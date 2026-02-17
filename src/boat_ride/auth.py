"""JWT verification: FastAPI dependencies for Supabase Auth.

- ``get_current_user``: requires a valid JWT, returns user_id (UUID str).
- ``get_optional_user``: returns user_id or None (for public endpoints).
"""
from __future__ import annotations

import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request

from boat_ride.config import settings

log = logging.getLogger(__name__)


def _extract_token(request: Request) -> Optional[str]:
    """Pull Bearer token from the Authorization header."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _decode_token(token: str) -> dict:
    """Decode and verify a Supabase JWT using HS256."""
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience="authenticated",
    )


async def get_current_user(request: Request) -> str:
    """FastAPI dependency — requires a valid JWT. Returns user_id (UUID str)."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    try:
        payload = _decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no sub claim")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_optional_user(request: Request) -> Optional[str]:
    """FastAPI dependency — returns user_id or None for unauthenticated callers."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = _decode_token(token)
        return payload.get("sub")
    except Exception:
        return None
