import time
from typing import Optional

import httpx
from jose import jwt, JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse

from ..config import settings
from ..logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# JWKS cache — fetched once, refreshed every 12 hours
# ---------------------------------------------------------------------------
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0
_JWKS_TTL = 43200  # 12 hours in seconds

# Paths that skip auth entirely
PUBLIC_PATHS = {"/", "/docs", "/openapi.json", "/redoc"}


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/api/v1/health")


async def _get_jwks() -> dict:
    """Fetch JWKS from iCM and cache it."""
    global _jwks_cache, _jwks_fetched_at

    if _jwks_cache and (time.time() - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache

    async with httpx.AsyncClient() as client:
        response = await client.get(settings.ICM_JWKS_URL, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_fetched_at = time.time()
        logger.info("JWKS refreshed from iCM")

    return _jwks_cache


async def _validate_via_endpoint(token: str) -> dict:
    """Fallback: validate token by calling iCM auth endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.ICM_AUTH_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code != 200:
            raise JWTError("Token rejected by iCM auth endpoint")
        return response.json()


def _validate_via_static_key(token: str) -> dict:
    """Validate JWT using a static public key provided by iCM."""
    kwargs = {"algorithms": [settings.JWT_ALGORITHM]}

    return jwt.decode(token, settings.ICM_PUBLIC_KEY, **kwargs)


async def _decode_token(token: str) -> dict:
    """Priority: static iCM endpoint → key."""
    if settings.ICM_AUTH_ENDPOINT:
        return await _validate_via_endpoint(token)
    if settings.ICM_PUBLIC_KEY:
        return _validate_via_static_key(token)
    raise JWTError("No iCM auth method configured")


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_public(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header.removeprefix("Bearer ").strip()

        try:
            claims = await _decode_token(token)
        except JWTError as e:
            logger.warning(f"JWT validation failed: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication service unavailable"},
            )

        # Set all extracted fields on request.state for downstream use
        request.state.user_id      = claims.get("user_id") or claims.get("sub")
        request.state.user_name    = claims.get("user_name") or claims.get("name")
        request.state.roles        = claims.get("roles", [])
        request.state.user_role    = claims.get("roles", [None])[0]  # primary role
        request.state.tenant_id    = claims.get("tenant_id")
        request.state.facility_id  = claims.get("facility_id")
        request.state.site_ids     = claims.get("site_ids", [])
        request.state.provider_id  = claims.get("provider_id")

        return await call_next(request)
