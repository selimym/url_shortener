from . import models
import random
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def generate_random_key(size: int = 6) -> str:
    """Generate a random key of uppercase letters and digits."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=size))


async def key_exists(db: AsyncSession, key: str) -> bool:
    """Check if a key already exists in the database."""
    stmt = select(models.URL).where(models.URL.key == key)
    result = await db.execute(stmt)
    return result.scalars().first() is not None


async def generate_unique_random_key(db: AsyncSession, size: int = 6) -> str:
    """Generate a unique random key that doesn't exist in the database."""
    key = generate_random_key(size)
    while await key_exists(db, key):
        key = generate_random_key(size)
    return key