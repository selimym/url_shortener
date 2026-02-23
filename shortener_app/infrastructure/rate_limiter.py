from fastapi import HTTPException, Request
from shortener_app.config import get_settings


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def check_rate_limit(self, request: Request):
        if not get_settings().rate_limit_enabled:
            return

        # IP-based limiting: without auth, the client's IP is the only available identifier.
        # Users behind the same NAT share one bucket — acceptable trade-off for a public API.
        redis = request.app.state.redis
        key = f"rate_limit:{request.client.host}:{request.url.path}"

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
