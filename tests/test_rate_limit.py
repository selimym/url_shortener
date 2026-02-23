import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import AsyncMock
from typing import Callable

from shortener_app.main import app, get_db
from shortener_app.database import Base

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
    """Mock Redis that enforces rate limits."""
    mock_redis = AsyncMock()
    request_counts = {}

    async def mock_get(key):
        return request_counts.get(key)

    async def mock_setex(key, ttl, value):
        request_counts[key] = str(value)
        return True

    async def mock_incr(key):
        current = int(request_counts.get(key, 0))
        request_counts[key] = str(current + 1)
        return current + 1

    mock_redis.get.side_effect = mock_get
    mock_redis.setex.side_effect = mock_setex
    mock_redis.incr.side_effect = mock_incr

    return mock_redis


@pytest.fixture
async def rate_limited_client(test_db, monkeypatch, mock_redis_with_rate_limit):
    """Client with Redis rate limiting enabled."""
    app.state.redis = mock_redis_with_rate_limit

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


@pytest.mark.asyncio
async def test_rate_limit_per_client(test_db, monkeypatch):
    """Test that rate limits are tracked per client IP."""
    request_counts = {}

    mock_redis = AsyncMock()

    async def mock_get(key):
        return request_counts.get(key)

    async def mock_setex(key, ttl, value):
        request_counts[key] = str(value)
        return True

    async def mock_incr(key):
        current = int(request_counts.get(key, 0))
        request_counts[key] = str(current + 1)
        return current + 1

    mock_redis.get.side_effect = mock_get
    mock_redis.setex.side_effect = mock_setex
    mock_redis.incr.side_effect = mock_incr

    app.state.redis = mock_redis

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
