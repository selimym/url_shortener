import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import Callable
from unittest.mock import AsyncMock

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


@pytest.fixture(scope="function")
async def client(test_db):
    """Provide test client with overridden dependencies."""
    # httpx's ASGITransport (>=0.24) does not run the FastAPI lifespan, so set
    # app.state.redis directly. In production the lifespan handles this.
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.incr.return_value = 1

    app.state.redis = mock_redis

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
