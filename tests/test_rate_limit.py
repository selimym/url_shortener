import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import AsyncMock, MagicMock
from typing import Callable

from shortener_app.main import app, get_db
from shortener_app.database import Base
from shortener_app.infrastructure import ClickBuffer
from shortener_app.infrastructure.rate_limiter import RateLimiter

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_db(test_engine):
    """Provide test database session."""
    TestSessionLocal: Callable[[], AsyncSession] = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    yield TestSessionLocal


@pytest.fixture
async def mock_redis_with_rate_limit():
    """Mock Redis that enforces rate limits using the INCR-first pattern."""
    mock_redis = AsyncMock()
    request_counts = {}

    async def mock_incr(key):
        current = int(request_counts.get(key, 0))
        request_counts[key] = str(current + 1)
        return current + 1

    async def mock_expire(key, ttl):
        return True

    mock_redis.incr.side_effect = mock_incr
    mock_redis.expire.side_effect = mock_expire

    return mock_redis


@pytest.fixture
async def rate_limited_client(test_db, monkeypatch, mock_redis_with_rate_limit):
    """Client with Redis rate limiting enabled."""
    app.state.redis = mock_redis_with_rate_limit
    app.state.click_buffer = ClickBuffer(mock_redis_with_rate_limit)

    from shortener_app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_create", 10)
    monkeypatch.setattr(settings, "rate_limit_read", 100)

    async def override_get_db():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
    del app.state.redis
    del app.state.click_buffer


@pytest.mark.asyncio
async def test_create_url_rate_limit_enforcement(rate_limited_client):
    """Test that POST /url enforces rate limit."""
    # Create URLs up to the limit (10)
    for i in range(10):
        response = await rate_limited_client.post(
            "/url",
            json={"target_url": f"https://example{i}.com"}
        )
        assert response.status_code == 200

    # 11th request should be rate limited
    response = await rate_limited_client.post(
        "/url",
        json={"target_url": "https://example-overflow.com"}
    )
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]


@pytest.mark.asyncio
async def test_read_url_rate_limit_enforcement(rate_limited_client):
    """Test that GET /{key} enforces rate limit."""
    # First create a URL
    response = await rate_limited_client.post(
        "/url",
        json={"target_url": "https://example.com"}
    )
    assert response.status_code == 200
    url_key = response.json()["url"].split("/")[-1]

    # Access URL up to the limit (100)
    for _ in range(99):  # We already made 1 POST which counts separately
        response = await rate_limited_client.get(f"/{url_key}")
        assert response.status_code in [200, 307]  # Redirect or OK

    # The next request should still work (we haven't hit GET limit yet)
    response = await rate_limited_client.get(f"/{url_key}")
    assert response.status_code in [200, 307]


@pytest.mark.asyncio
async def test_rate_limit_returns_429(rate_limited_client):
    """Test that rate limit returns HTTP 429 status."""
    # Exhaust the rate limit
    for i in range(10):
        await rate_limited_client.post(
            "/url",
            json={"target_url": f"https://example{i}.com"}
        )

    # Next request should return 429
    response = await rate_limited_client.post(
        "/url",
        json={"target_url": "https://overflow.com"}
    )
    assert response.status_code == 429
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_rate_limit_disabled(test_db, monkeypatch):
    """Test that rate limiting can be disabled via config."""
    mock_redis = AsyncMock()
    app.state.redis = mock_redis
    app.state.click_buffer = ClickBuffer(mock_redis)

    from shortener_app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    async def override_get_db():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Make many requests (more than limit)
        for i in range(15):
            response = await client.post(
                "/url",
                json={"target_url": f"https://example{i}.com"}
            )
            assert response.status_code == 200

    app.dependency_overrides.clear()
    del app.state.redis
    del app.state.click_buffer


@pytest.mark.asyncio
async def test_rate_limit_per_client(test_db, monkeypatch):
    """Test that rate limits are tracked per client IP."""
    request_counts = {}

    mock_redis = AsyncMock()

    async def mock_incr(key):
        current = int(request_counts.get(key, 0))
        request_counts[key] = str(current + 1)
        return current + 1

    async def mock_expire(key, ttl):
        return True

    mock_redis.incr.side_effect = mock_incr
    mock_redis.expire.side_effect = mock_expire

    app.state.redis = mock_redis
    app.state.click_buffer = ClickBuffer(mock_redis)

    from shortener_app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def override_get_db():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Verify that keys are created for the rate limiter (IP + path format)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        await client.post("/url", json={"target_url": "https://example.com"})

    # Key format is now "rate_limit:{ip}:{path}" — human-readable, no MD5
    assert len(request_counts) > 0
    assert any(k.startswith("rate_limit:") for k in request_counts)

    app.dependency_overrides.clear()
    del app.state.redis
    del app.state.click_buffer


# ── Unit tests for the two rate-limiter bugs ──────────────────────────────────
#
# These test RateLimiter directly with controlled mocks, so they don't need the
# full HTTP stack. Each test documents the original bug in a comment, then
# verifies that the fixed INCR-first pattern behaves correctly.

def _make_mock_request(mock_redis, ip="127.0.0.1", path="/url"):
    request = MagicMock()
    request.app.state.redis = mock_redis
    request.client.host = ip
    request.url.path = path
    return request


@pytest.mark.asyncio
async def test_rate_limit_expire_called_for_new_key(monkeypatch):
    """
    Bug (old GET → check → SETEX/INCR pattern):

        GET key → None
        SETEX key 60 1       ← TTL set here, fine

        BUT: if the key expired between a GET (that returned a value) and the
        subsequent INCR, the INCR created a new key with *no TTL*. That counter
        would then persist forever, permanently rate-limiting the user until a
        Redis restart.

    Fix (INCR-first):

        INCR key → 1  (new key created)
        EXPIRE key 60  ← TTL always set when count == 1

    INCR returns 1 only when the key did not previously exist, so EXPIRE is
    called on every new key with no gap for the TTL-less state to persist.
    This test verifies that expire() is called after incr() returns 1.
    """
    from shortener_app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1   # first request — new key
    mock_redis.expire.return_value = True

    limiter = RateLimiter(max_requests=10)
    await limiter.check_rate_limit(_make_mock_request(mock_redis))

    mock_redis.expire.assert_called_once_with("rate_limit:127.0.0.1:/url", 60)


@pytest.mark.asyncio
async def test_rate_limit_expire_not_called_for_existing_key(monkeypatch):
    """
    expire() must only be called when INCR creates a new key (count == 1).

    For subsequent requests in the same window (count > 1), the TTL is already
    set. Calling EXPIRE again would reset the sliding window, leaking extra
    quota to the user. Verify expire() is skipped for mid-window requests.
    """
    from shortener_app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 5   # existing key, mid-window
    mock_redis.expire.return_value = True

    limiter = RateLimiter(max_requests=10)
    await limiter.check_rate_limit(_make_mock_request(mock_redis))

    mock_redis.expire.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_overflow_impossible_with_atomic_incr(monkeypatch):
    """
    Bug (old GET → check → INCR pattern):

        Request A: GET key → 9   (9 < limit=10, passes check)
                                  ← race window: B slips in before A's INCR
        Request B: GET key → 9   (9 < limit=10, passes check)
        Request A: INCR key → 10  ✓ allowed
        Request B: INCR key → 11  ✓ also allowed — limit silently exceeded

    Both requests saw the same pre-increment count, both passed the check, and
    both incremented. The limit was bypassed with no error returned.

    Fix (INCR-first):

        Request A: INCR key → 10  (10 == limit, still allowed)
        Request B: INCR key → 11  (11 > limit → 429)

    INCR is atomic: the returned value IS the post-increment count. No two
    concurrent requests can both observe the same post-increment value.

    This test simulates "request B": INCR already returned 11, which exceeds
    the limit, so a 429 must be raised — and no GET was involved.
    """
    from shortener_app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 11  # count already over the limit
    mock_redis.expire.return_value = True

    limiter = RateLimiter(max_requests=10)
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check_rate_limit(_make_mock_request(mock_redis))

    assert exc_info.value.status_code == 429
    # Verify the INCR-first pattern: INCR was called, GET was not.
    mock_redis.incr.assert_called_once()
    mock_redis.get.assert_not_called()
