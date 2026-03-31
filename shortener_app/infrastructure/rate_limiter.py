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
        key = f"rate_limit:{request.client.host}:{path}"

        # INCR is atomic — the returned count is the authoritative gate.
        # The old GET → check → SETEX/INCR pattern had two bugs:
        #   1. Non-atomic: two concurrent requests could both read count=limit-1,
        #      both pass the check, and both INCR — silently exceeding the limit.
        #   2. Missing TTL: if the key expired between GET (returned a value)
        #      and INCR, the INCR created a new key with no expiry, permanently
        #      rate-limiting the user.
        count = await redis.incr(key)
        if count == 1:
            # New key — set the expiry window. INCR returning 1 means this is
            # the first request; the key did not exist before this call.
            # The tiny gap between INCR and EXPIRE (crash = key with no TTL)
            # is accepted; eliminating it would require a Lua script.
            await redis.expire(key, self.window_seconds)
        if count > self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s"
            )
