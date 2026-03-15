import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import Callable

from shortener_app.main import app, get_db
from shortener_app.database import Base
from shortener_app.infrastructure import ClickBuffer


class FakeRedis:
    """Minimal stateful Redis fake. Implements only the subset used by RateLimiter and ClickBuffer."""

    def __init__(self):
        self._strings: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    # Rate-limiter methods are no-ops so general tests never hit a rate limit.
    # Rate limiting behaviour is tested separately in test_rate_limit.py.
    async def get(self, key: str):
        return None

    async def setex(self, key: str, ttl: int, value):
        pass

    async def incr(self, key: str) -> int:
        return 1

    async def zincrby(self, key: str, amount: float, member) -> float:
        zset = self._zsets.setdefault(key, {})
        zset[str(member)] = zset.get(str(member), 0.0) + float(amount)
        return zset[str(member)]

    async def zscore(self, key: str, member):
        return self._zsets.get(key, {}).get(str(member))

    def _sorted_items(self, key: str, reverse: bool):
        return sorted(self._zsets.get(key, {}).items(), key=lambda x: x[1], reverse=reverse)

    async def zrange(self, key: str, start: int, end: int, withscores: bool = False):
        items = self._sorted_items(key, reverse=False)
        items = items[start:] if end == -1 else items[start:end + 1]
        return items if withscores else [k for k, _ in items]

    async def zrevrange(self, key: str, start: int, end: int, withscores: bool = False):
        items = self._sorted_items(key, reverse=True)
        items = items[start:] if end == -1 else items[start:end + 1]
        return items if withscores else [k for k, _ in items]

    async def rename(self, src: str, dst: str):
        if src not in self._zsets and src not in self._strings:
            raise Exception("ERR no such key")
        if src in self._zsets:
            self._zsets[dst] = self._zsets.pop(src)
        if src in self._strings:
            self._strings[dst] = self._strings.pop(src)

    async def exists(self, *keys: str) -> int:
        return sum(1 for k in keys if k in self._zsets or k in self._strings)

    async def expire(self, key: str, seconds: int) -> bool:
        # TTL tracking not needed for tests; just acknowledge the call.
        return key in self._zsets or key in self._strings

    async def delete(self, *keys: str):
        for key in keys:
            self._zsets.pop(key, None)
            self._strings.pop(key, None)

    async def close(self):
        pass

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
    # app.state manually. In production the lifespan handles this.
    fake_redis = FakeRedis()
    app.state.redis = fake_redis
    app.state.click_buffer = ClickBuffer(fake_redis)

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
