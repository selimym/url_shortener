from redis.asyncio import Redis
from shortener_app.config import get_settings


async def create_redis_client() -> Redis:
    return Redis.from_url(
        get_settings().redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
