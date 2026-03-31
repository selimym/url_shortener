import asyncio
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shortener_app import keygen, models


class URLService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_key(self, key: str, active_only: bool = True) -> Optional[models.URL]:
        stmt = select(models.URL).where(models.URL.key == key)
        if active_only:
            stmt = stmt.where(models.URL.is_active == True)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_secret_key(self, secret_key: str) -> Optional[models.URL]:
        stmt = select(models.URL).where(
            models.URL.secret_key == secret_key,
            models.URL.is_active == True
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create(self, target_url: str, max_retries: int = 5) -> models.URL:
        """Generate random key and let database unique constraint catch collisions.

        Avoids TOCTOU race: checking if key exists, then inserting it, leaves a gap
        where another request can insert the same key. Instead, we try to insert
        and catch IntegrityError, retrying with exponential backoff on collision.
        """
        for attempt in range(max_retries):
            try:
                key = keygen.generate_random_key(size=6)
                secret_key = f"{key}_{keygen.generate_random_key(size=8)}"
                db_url = models.URL(target_url=target_url, key=key, secret_key=secret_key)
                self.db.add(db_url)
                await self.db.commit()
                await self.db.refresh(db_url)
                return db_url
            except IntegrityError:
                await self.db.rollback()
                if attempt == max_retries - 1:
                    raise ValueError("Failed to generate unique key after retries")
                await asyncio.sleep(0.01 * (2 ** attempt))  # exponential backoff
        raise RuntimeError("Failed to generate unique key")

    async def deactivate(self, secret_key: str) -> Optional[models.URL]:
        db_url = await self.get_by_secret_key(secret_key)
        if db_url:
            db_url.is_active = False
            await self.db.commit()
            await self.db.refresh(db_url)
        return db_url
