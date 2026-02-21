"""User profile endpoints: GET /profiles/me, PUT /profiles/me, DELETE /account/me."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boat_ride.auth import get_current_user
from boat_ride.db import get_supabase

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileOut(BaseModel):
    id: str
    display_name: Optional[str] = None
    experience_level: Optional[str] = None
    home_region: Optional[str] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    units: Optional[str] = None


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    experience_level: Optional[str] = None
    home_region: Optional[str] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    units: Optional[str] = None


@router.get("/me", response_model=ProfileOut)
def get_my_profile(user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = sb.table("profiles").select("*").eq("id", user_id).single().execute()
    return resp.data


@router.put("/me", response_model=ProfileOut)
def update_my_profile(
    body: ProfileUpdate,
    user_id: str = Depends(get_current_user),
):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    resp = (
        sb.table("profiles")
        .update(updates)
        .eq("id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return resp.data[0]


@router.delete("/account/me", status_code=204)
def delete_my_account(user_id: str = Depends(get_current_user)):
    """Permanently delete the authenticated user's account and all associated data."""
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    sb.auth.admin.delete_user(user_id)
    return None
