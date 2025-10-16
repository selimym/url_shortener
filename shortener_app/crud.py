from . import keygen, models, schemas

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_db_url(db: AsyncSession, url: schemas.URLBase) -> models.URL:
    key = await keygen.generate_unique_random_key(db, size=6)
    secret_key = f"{key}_{keygen.generate_random_key(size=8)}"
    db_url = models.URL(
        target_url=url.target_url, key=key, secret_key=secret_key
    )
    db.add(db_url)
    await db.commit()
    await db.refresh(db_url)
    return db_url


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
    db_url.clicks += 1
    await db.commit()
    await db.refresh(db_url)
    return db_url
