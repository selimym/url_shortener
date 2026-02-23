from fastapi import HTTPException, Request
from shortener_app.infrastructure.redis_client import get_redis
from shortener_app.config import get_settings
import hashlib

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def check_rate_limit(self, request: Request):
        if not get_settings().rate_limit_enabled:
            return

        redis = await get_redis()
        identifier = f"{request.client.host}:{request.url.path}"
        key = f"rate_limit:{hashlib.md5(identifier.encode()).hexdigest()}"

        current = await redis.get(key)
        if current is None:
            await redis.setex(key, self.window_seconds, 1)
        elif int(current) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s"
            )
        else:
            await redis.incr(key)
