from . import keygen, models, schemas

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio


async def create_db_url(db: AsyncSession, url: schemas.URLBase, max_retries: int = 5) -> models.URL:
    for attempt in range(max_retries):
        try:
            # Generate key without database check (remove TOCTOU)
            key = keygen.generate_random_key(size=6)
            secret_key = f"{key}_{keygen.generate_random_key(size=8)}"
            db_url = models.URL(
                target_url=url.target_url, key=key, secret_key=secret_key
            )
            db.add(db_url)
            await db.commit()
            await db.refresh(db_url)
            return db_url
        except IntegrityError:
            await db.rollback()
            if attempt == max_retries - 1:
                raise ValueError("Failed to generate unique key after multiple attempts")
            await asyncio.sleep(0.01 * (2 ** attempt))  # Exponential backoff
    raise RuntimeError("Failed to generate unique key")


async def get_db_url_by_key(db: AsyncSession, url_key: str) -> models.URL | None:
    stmt = select(models.URL).where(
        models.URL.key == url_key,
        models.URL.is_active == True
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_db_url_by_id(db: AsyncSession, url_id: int) -> models.URL | None:
    return await db.get(models.URL, url_id)


async def get_db_url_by_secret_key(db: AsyncSession, secret_key: str) -> models.URL | None:
    stmt = select(models.URL).where(
        models.URL.secret_key == secret_key,
        models.URL.is_active == True
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def deactivate_db_url(db: AsyncSession, secret_key: str) -> models.URL | None:
    db_url = await get_db_url_by_secret_key(db, secret_key)
    if db_url:
        db_url.is_active = False
        await db.commit()
        await db.refresh(db_url)
    return db_url


async def update_db_clicks(db: AsyncSession, db_url: models.URL) -> models.URL:
    stmt = (
        update(models.URL)
        .where(models.URL.id == db_url.id)
        .values(clicks=models.URL.clicks + 1)
        .returning(models.URL)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()
