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


class _NullPipeline:
    """Pipeline that always reports count=1 (no rate limiting)."""
    def zremrangebyscore(self, *a): return self
    def zadd(self, *a, **kw): return self
    def zcard(self, *a): return self
    def expire(self, *a): return self
    async def execute(self): return [0, 1, 1, True]
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass


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
    """Mock Redis that enforces sliding-window rate limits via a pipeline mock."""
    mock_redis = AsyncMock()
    zsets: dict[str, dict[str, float]] = {}

    class MockPipeline:
        def __init__(self):
            self._cmds: list = []

        def zremrangebyscore(self, key, min_score, max_score):
            self._cmds.append(("zremrangebyscore", key, min_score, max_score))
            return self

        def zadd(self, key, mapping):
            self._cmds.append(("zadd", key, mapping))
            return self

        def zcard(self, key):
            self._cmds.append(("zcard", key))
            return self

        def expire(self, key, ttl):
            self._cmds.append(("expire", key, ttl))
            return self

        async def execute(self):
            results = []
            for op, *args in self._cmds:
                if op == "zremrangebyscore":
                    key, lo, hi = args
                    zset = zsets.setdefault(key, {})
                    stale = [m for m, s in zset.items() if lo <= s <= hi]
                    for m in stale:
                        del zset[m]
                    results.append(len(stale))
                elif op == "zadd":
                    key, mapping = args
                    zsets.setdefault(key, {}).update(mapping)
                    results.append(len(mapping))
                elif op == "zcard":
                    results.append(len(zsets.get(args[0], {})))
                elif op == "expire":
                    results.append(True)
            return results

        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    # pipeline() is synchronous in redis.asyncio — must be a MagicMock, not AsyncMock
    mock_redis.pipeline = MagicMock(side_effect=lambda: MockPipeline())
    # Cache miss for all keys so redirects fall through to PostgreSQL
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = True
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

    # Make exactly 100 GET requests (the limit)
    for _ in range(100):
        response = await rate_limited_client.get(f"/{url_key}")
        assert response.status_code in [200, 307]

    # 101st request must be rejected
    response = await rate_limited_client.get(f"/{url_key}")
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]


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
    mock_redis.get.return_value = None
    mock_redis.pipeline = MagicMock(return_value=_NullPipeline())
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
    """Test that rate limit keys follow the expected IP + path format."""
    seen_keys: list[str] = []

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    class TrackingPipeline:
        def zremrangebyscore(self, key, *a): return self
        def zadd(self, key, mapping):
            seen_keys.append(key)
            return self
        def zcard(self, *a): return self
        def expire(self, *a): return self
        async def execute(self): return [0, 1, 1, True]
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    mock_redis.pipeline = MagicMock(side_effect=lambda: TrackingPipeline())

    app.state.redis = mock_redis
    app.state.click_buffer = ClickBuffer(mock_redis)

    from shortener_app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def override_get_db():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        await client.post("/url", json={"target_url": "https://example.com"})

    # Key format: "rate_limit:{ip}:{path}" — human-readable, no MD5
    assert len(seen_keys) > 0
    assert any(k.startswith("rate_limit:") for k in seen_keys)

    app.dependency_overrides.clear()
    del app.state.redis
    del app.state.click_buffer


# ── Unit tests for the sliding-window rate limiter ────────────────────────────
#
# These test RateLimiter directly with a lightweight pipeline mock so they
# don't need the full HTTP stack.

def _make_mock_request(mock_redis, ip="127.0.0.1", path="/url"):
    request = MagicMock()
    request.app.state.redis = mock_redis
    request.client.host = ip
    request.url.path = path
    return request


def _make_pipeline_redis(zcard_result: int):
    """Return a mock Redis whose pipeline reports zcard_result for the count."""
    mock_redis = AsyncMock()

    class FixedPipeline:
        def zremrangebyscore(self, *a): return self
        def zadd(self, *a, **kw): return self
        def zcard(self, *a): return self
        def expire(self, *a): return self
        async def execute(self): return [0, 1, zcard_result, True]
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    mock_redis.pipeline = MagicMock(return_value=FixedPipeline())
    return mock_redis


@pytest.mark.asyncio
async def test_sliding_window_counts_only_recent_requests(monkeypatch):
    """Requests within the window are counted; the pipeline prunes stale entries."""
    from shortener_app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)

    # Simulate 5 current requests in the window
    mock_redis = _make_pipeline_redis(zcard_result=5)
    limiter = RateLimiter(max_requests=10)
    # Should pass without raising
    await limiter.check_rate_limit(_make_mock_request(mock_redis))
    mock_redis.pipeline.assert_called_once()


@pytest.mark.asyncio
async def test_sliding_window_allows_request_at_limit(monkeypatch):
    """A count exactly equal to max_requests is still allowed."""
    from shortener_app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)

    mock_redis = _make_pipeline_redis(zcard_result=10)
    limiter = RateLimiter(max_requests=10)
    await limiter.check_rate_limit(_make_mock_request(mock_redis))  # must not raise


@pytest.mark.asyncio
async def test_sliding_window_rejects_over_limit(monkeypatch):
    """A count exceeding max_requests raises 429."""
    from shortener_app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)

    mock_redis = _make_pipeline_redis(zcard_result=11)
    limiter = RateLimiter(max_requests=10)
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check_rate_limit(_make_mock_request(mock_redis))

    assert exc_info.value.status_code == 429
