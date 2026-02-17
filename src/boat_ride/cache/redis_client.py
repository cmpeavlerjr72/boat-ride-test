"""Redis connection + JSON/text cache helpers.

All operations are wrapped in try/except — Redis failure never breaks the app.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

_redis_client = None
_redis_checked = False


def get_redis():
    """Lazy singleton.  Returns ``redis.Redis`` or ``None`` if unavailable."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        from boat_ride.config import settings

        if not settings.redis_url:
            return None
        import redis

        _redis_client = redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=3
        )
        _redis_client.ping()
        log.info("Redis connected: %s", settings.redis_url)
    except Exception as exc:
        log.warning("Redis unavailable (%s), running without cache", exc)
        _redis_client = None
    return _redis_client


# ── JSON helpers ─────────────────────────────────────────────────────────

def cache_get_json(key: str) -> Optional[Any]:
    try:
        r = get_redis()
        if r is None:
            return None
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


def cache_set_json(key: str, value: Any, ttl: int) -> None:
    try:
        r = get_redis()
        if r is None:
            return
        r.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass


# ── Text helpers ─────────────────────────────────────────────────────────

def cache_get_text(key: str) -> Optional[str]:
    try:
        r = get_redis()
        if r is None:
            return None
        return r.get(key)
    except Exception:
        return None


def cache_set_text(key: str, value: str, ttl: int) -> None:
    try:
        r = get_redis()
        if r is None:
            return
        r.set(key, value, ex=ttl)
    except Exception:
        pass
