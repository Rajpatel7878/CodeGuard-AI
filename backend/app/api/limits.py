"""Shared rate limiter.

A single limiter instance is attached to ``app.state`` and reused by the route
modules, so limits and the ``RateLimitExceeded`` handler always agree.
Set ``RATE_LIMIT_ENABLED=false`` to disable limits (used by the test suite).
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)

__all__ = ["limiter"]
