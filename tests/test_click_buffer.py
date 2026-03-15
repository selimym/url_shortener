"""
Unit tests for ClickBuffer, focused on the two durability bugs found in flush_to_db.

Each test documents the original bug in its docstring, then verifies that the
fixed implementation handles it correctly.
"""
import pytest
from unittest.mock import AsyncMock

from shortener_app.infrastructure.click_buffer import ClickBuffer, _FLUSH_KEY, _LEADERBOARD_KEY
from shortener_app.services import URLService
from shortener_app import models
from tests.conftest import FakeRedis


async def _create_url(factory) -> models.URL:
    async with factory() as db:
        return await URLService(db).create("https://example.com")


@pytest.mark.asyncio
async def test_flush_normal_path(test_db):
    """Baseline: a successful flush commits all buffered clicks and cleans up Redis."""
    redis = FakeRedis()
    buffer = ClickBuffer(redis)
    url = await _create_url(test_db)

    await buffer.increment(url.id)
    await buffer.increment(url.id)
    await buffer.increment(url.id)

    async with test_db() as db:
        await buffer.flush_to_db(db)

    assert await redis.exists(_FLUSH_KEY) == 0
    assert await redis.exists(_LEADERBOARD_KEY) == 0

    async with test_db() as db:
        result = await db.get(models.URL, url.id)
        assert result.clicks == 3


@pytest.mark.asyncio
async def test_flush_does_not_lose_clicks_on_db_failure(test_db):
    """
    Bug (old `finally: delete` pattern):

        try:
            entries = redis.zrange(_FLUSH_KEY, ...)
            for ...:
                await db.execute(...)
            await db.commit()         ← raises on a transient DB error
        finally:
            await redis.delete(_FLUSH_KEY)  ← runs anyway, clicks gone forever

    After RENAME, _FLUSH_KEY holds all buffered clicks. A transient DB error
    (connection drop, deadlock, disk full) caused the finally block to delete
    _FLUSH_KEY regardless — silently discarding the entire batch.

    Fix: Only delete _FLUSH_KEY *after* a confirmed successful commit. If
    commit() raises, the key persists so the next flush_to_db call recovers it.

    This test:
      1. Buffers 2 clicks.
      2. Forces the first flush to fail at commit().
      3. Verifies _FLUSH_KEY still exists (clicks not lost).
      4. Runs a second flush successfully — verifies all clicks are persisted.
    """
    redis = FakeRedis()
    buffer = ClickBuffer(redis)
    url = await _create_url(test_db)

    await buffer.increment(url.id)
    await buffer.increment(url.id)

    # First flush — commit() fails
    async with test_db() as db:
        db.commit = AsyncMock(side_effect=Exception("Simulated DB failure"))
        with pytest.raises(Exception, match="Simulated DB failure"):
            await buffer.flush_to_db(db)

    # _FLUSH_KEY must still hold the 2 clicks; they were not discarded
    assert await redis.exists(_FLUSH_KEY) == 1, (
        "_FLUSH_KEY was deleted despite failed commit — clicks lost forever"
    )

    # Second flush — succeeds; stale key is recovered and persisted
    async with test_db() as db:
        await buffer.flush_to_db(db)

    assert await redis.exists(_FLUSH_KEY) == 0

    async with test_db() as db:
        result = await db.get(models.URL, url.id)
        assert result.clicks == 2, (
            f"Expected 2 clicks after recovery, got {result.clicks}"
        )


@pytest.mark.asyncio
async def test_flush_recovers_stale_flush_key(test_db):
    """
    Bug (missing stale-key recovery):

        Timeline:
          flush_to_db():
            RENAME _LEADERBOARD_KEY → _FLUSH_KEY   ← atomic, succeeds
            db.commit()                             ← process crashes here
          ... process restarts ...
          flush_to_db():
            RENAME _LEADERBOARD_KEY → _FLUSH_KEY   ← overwrites stale key!
            db.commit()                             ← only new clicks persisted

        The stale clicks (from before the crash) were silently overwritten by
        the RENAME on the next flush and are permanently lost.

    Fix: At the start of flush_to_db(), check for an existing _FLUSH_KEY.
    If found, process (drain) it first before starting a new flush window.

    This test simulates the post-crash state:
      - _FLUSH_KEY has 2 stale clicks (RENAME succeeded, commit crashed)
      - _LEADERBOARD_KEY has 3 new clicks that arrived after the crash
    Both batches must be committed to the database.
    """
    redis = FakeRedis()
    buffer = ClickBuffer(redis)
    url = await _create_url(test_db)

    # Simulate state after a mid-flush crash: stale key + fresh clicks
    await redis.zincrby(_FLUSH_KEY, 2, url.id)       # stranded from crashed flush
    await redis.zincrby(_LEADERBOARD_KEY, 3, url.id)  # new clicks after restart

    async with test_db() as db:
        await buffer.flush_to_db(db)

    # Both batches must be persisted: 2 stale + 3 new = 5
    async with test_db() as db:
        result = await db.get(models.URL, url.id)
        assert result.clicks == 5, (
            f"Expected 5 clicks (2 stale + 3 new), got {result.clicks}. "
            "Stale flush key was not recovered."
        )

    assert await redis.exists(_FLUSH_KEY) == 0
    assert await redis.exists(_LEADERBOARD_KEY) == 0
