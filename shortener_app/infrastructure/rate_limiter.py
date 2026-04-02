import time

from fastapi import HTTPException, Request
from shortener_app.config import get_settings


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def check_rate_limit(self, request: Request, endpoint: str | None = None):
        if not get_settings().rate_limit_enabled:
            return

        # IP-based limiting: without auth, the client's IP is the only available identifier.
        # Users behind the same NAT share one bucket — acceptable trade-off for a public API.
        # endpoint overrides the path component so wildcard routes like /admin/{secret}
        # share one bucket per IP instead of one per unique secret (which would allow
        # unlimited brute-force attempts across different secrets).
        redis = request.app.state.redis
        path = endpoint if endpoint is not None else request.url.path
        # request.client is None when the ASGI transport omits peer info (e.g. some test
        # clients). Fall back to "unknown" so the key is still valid rather than crashing.
        client_host = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_host}:{path}"

        # Sliding window via sorted set: each request is a member scored by its Unix
        # timestamp. Entries older than window_seconds are pruned before counting, so
        # the limit applies to a true rolling window rather than a fixed bucket that
        # resets on a schedule (which would allow 2× the limit across a reset boundary).
        now = time.time()
        async with redis.pipeline() as pipe:
            # Subtract 1 ns so the boundary entry (exactly window_seconds old) is kept
            # in the set and counted — making the window truly inclusive on both ends.
            pipe.zremrangebyscore(key, 0, now - self.window_seconds - 1e-9)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, self.window_seconds)
            results = await pipe.execute()
        count = results[2]
        if count > self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s"
            )
