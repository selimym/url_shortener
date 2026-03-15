import logging

from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from shortener_app import models

logger = logging.getLogger(__name__)

_LEADERBOARD_KEY = "clicks:leaderboard"
_FLUSH_KEY = "clicks:leaderboard:flushing"


class ClickBuffer:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def increment(self, url_id: int):
        await self.redis.zincrby(_LEADERBOARD_KEY, 1, url_id)

    async def get_count(self, url_id: int) -> int:
        """Return the buffered (unflushed) click count for a single URL."""
        score = await self.redis.zscore(_LEADERBOARD_KEY, url_id)
        return int(score) if score is not None else 0

    async def get_top_n(self, n: int) -> list[tuple[str, float]]:
        """Return (url_id, click_delta) pairs for the N most clicked URLs since last flush."""
        return await self.redis.zrevrange(_LEADERBOARD_KEY, 0, n - 1, withscores=True)

    async def flush_to_db(self, db: AsyncSession):
        # Bug fix: if the previous flush crashed after RENAME but before db.commit(),
        # _FLUSH_KEY is stranded. Without this check, the next RENAME would silently
        # overwrite it, permanently losing the clicks from that crashed batch.
        if await self.redis.exists(_FLUSH_KEY):
            logger.warning("Found stale flush key — recovering from previous failed flush")
            await self._drain_to_db(_FLUSH_KEY, db)

        try:
            # Atomically hand off the active key so clicks during the flush go to a fresh key.
            await self.redis.rename(_LEADERBOARD_KEY, _FLUSH_KEY)
        except Exception:
            return  # Key doesn't exist — nothing buffered since last flush

        await self._drain_to_db(_FLUSH_KEY, db)

    async def _drain_to_db(self, key: str, db: AsyncSession):
        entries = await self.redis.zrange(key, 0, -1, withscores=True)
        if not entries:
            await self.redis.delete(key)
            return
        for url_id, delta in entries:
            await db.execute(
                update(models.URL)
                .where(models.URL.id == int(url_id))
                .values(clicks=models.URL.clicks + int(delta))
            )
        await db.commit()
        # Bug fix: only delete the flush key after a confirmed successful commit.
        # The old `finally: delete` ran even when commit() raised, silently
        # discarding every click in that batch. Now, if commit() raises, the key
        # persists and will be recovered by the stale-key check on the next call.
        await self.redis.delete(key)
        logger.info("Flushed click counts for %d URLs", len(entries))
