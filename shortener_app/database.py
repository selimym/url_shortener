from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import Callable

from config import get_settings

# For SQLite with async support, use aiosqlite
# For PostgreSQL, use asyncpg
engine = create_async_engine(
    get_settings().db_url,
    echo=True,
)

AsyncSessionLocal: Callable[[], AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()