from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..redis import redis_client

USER_LIMIT = 100       # requests per minute per user
FACILITY_LIMIT = 1000  # requests per minute per facility
WINDOW = 60            # seconds


async def _check_limit(key: str, limit: int) -> bool:
    """Returns True if limit is exceeded."""
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, WINDOW)
    return count > limit


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Prefer IDs set by auth middleware on request.state, fall back to headers
        user_id = getattr(request.state, "user_id", None) or request.headers.get("X-User-ID")
        facility_id = getattr(request.state, "facility_id", None) or request.headers.get("X-Facility-ID")

        if user_id:
            if await _check_limit(f"rate:user:{user_id}", USER_LIMIT):
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"User rate limit exceeded. Max {USER_LIMIT} requests/min."},
                )

        if facility_id:
            if await _check_limit(f"rate:facility:{facility_id}", FACILITY_LIMIT):
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Facility rate limit exceeded. Max {FACILITY_LIMIT} requests/min."},
                )

        return await call_next(request)
