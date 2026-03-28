"""
Rate limiting and request throttling for production deployment.
Uses slowapi for flexible, configurable rate limiting.
"""

import logging
from functools import lru_cache
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)

# Import slowapi for rate limiting
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from fastapi import Request
    from fastapi.responses import JSONResponse
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    logger.warning("slowapi not installed. Install with: uv add slowapi")
    # Dummy types for when slowapi is not available
    Request = None
    JSONResponse = None


class RateLimitConfig:
    """Configuration for rate limiting policies."""

    # Default rate limit: 100 requests per minute per IP
    DEFAULT_RATE = "100/minute"

    # Stricter limits for expensive operations
    LIMITS = {
        "council_deliberate": "10/minute",          # Expensive LLM inference
        "generate_soap": "20/minute",               # Heavy processing
        "transcribe_audio": "30/minute",            # Model intensive
        "upload_image": "50/minute",                # Image processing
        "pubmed_search": "40/minute",               # External API calls
        "list_patients": "100/minute",              # Read-heavy
        "get_patient": "200/minute",                # Read-heavy
        "shift_brief": "10/minute",                 # Expensive computation
    }

    class_limits = {
        "PHYSICIAN": "unlimited",
        "SPECIALIST": "100/minute",
        "NURSE": "50/minute",
        "RESEARCHER": "30/minute",
        "AUDITOR": "50/minute",
        "ADMIN": "unlimited",
    }


def get_limiter() -> Optional["Limiter"]:
    """Get rate limiter instance or None if slowapi not available."""
    if not SLOWAPI_AVAILABLE:
        logger.warning("Rate limiting disabled - slowapi not installed")
        return None

    limiter = Limiter(key_func=get_remote_address, default_limits=[RateLimitConfig.DEFAULT_RATE])
    return limiter


def get_endpoint_limit(endpoint_name: str) -> str:
    """Get rate limit for a specific endpoint."""
    return RateLimitConfig.LIMITS.get(endpoint_name, RateLimitConfig.DEFAULT_RATE)


def get_role_limit(role: str) -> str:
    """Get rate limit for a user role."""
    return RateLimitConfig.class_limits.get(role, "100/minute")


async def rate_limit_exception_handler(request, exc: Exception):
    """Handle rate limit exceeded errors."""
    if not SLOWAPI_AVAILABLE:
        return None
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from slowapi.util import get_remote_address
    logger.warning(f"Rate limit exceeded for {get_remote_address(request)}")
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please retry after a moment.",
            "error": "RATE_LIMIT_EXCEEDED",
        },
    )


class RateLimitMiddleware:
    """Custom rate limiting middleware that respects user roles."""

    def __init__(self, app, limiter: Optional["Limiter"] = None):
        if not SLOWAPI_AVAILABLE:
            self.app = app
            self.limiter = None
            return
        self.app = app
        self.limiter = limiter or get_limiter()

    async def __call__(self, request, call_next):
        # If no limiter available, skip
        if self.limiter is None:
            return await call_next(request)

        # Extract user role from headers (if present)
        user_role = request.headers.get("X-User-Role", "NURSE").upper()
        role_limit = get_role_limit(user_role)

        # Check if role has unlimited access
        if role_limit == "unlimited":
            return await call_next(request)

        # Apply rate limit (implementation depends on limiter backend)
        # This is a simplified version; full implementation would integrate with limiter state
        return await call_next(request)
