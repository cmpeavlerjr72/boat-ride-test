"""Boat profile CRUD + public presets endpoint."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from boat_ride.auth import get_current_user
from boat_ride.db import get_supabase

router = APIRouter(prefix="/boats", tags=["boats"])


class BoatOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    is_preset: bool = False
    name: str
    boat_type: Optional[str] = None
    length_ft: Optional[float] = None
    beam_ft: Optional[float] = None
    draft_ft: Optional[float] = None
    max_safe_wind_kt: Optional[float] = None
    max_safe_wave_ft: Optional[float] = None
    comfort_bias: Optional[float] = None


class BoatCreate(BaseModel):
    name: str
    boat_type: str = "other"
    length_ft: Optional[float] = None
    beam_ft: Optional[float] = None
    draft_ft: Optional[float] = None
    max_safe_wind_kt: float = 25
    max_safe_wave_ft: float = 4.0
    comfort_bias: float = Field(default=0.0, ge=-1.0, le=1.0)


class BoatUpdate(BaseModel):
    name: Optional[str] = None
    boat_type: Optional[str] = None
    length_ft: Optional[float] = None
    beam_ft: Optional[float] = None
    draft_ft: Optional[float] = None
    max_safe_wind_kt: Optional[float] = None
    max_safe_wave_ft: Optional[float] = None
    comfort_bias: Optional[float] = None


# --- Public ---

@router.get("/presets", response_model=List[BoatOut])
def list_preset_boats():
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = sb.table("boat_profiles").select("*").eq("is_preset", True).execute()
    return resp.data


# --- Authenticated ---

@router.get("", response_model=List[BoatOut])
def list_my_boats(user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = (
        sb.table("boat_profiles")
        .select("*")
        .or_(f"is_preset.eq.true,user_id.eq.{user_id}")
        .execute()
    )
    return resp.data


@router.post("", response_model=BoatOut, status_code=201)
def create_boat(body: BoatCreate, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    row = body.model_dump()
    row["user_id"] = user_id
    row["is_preset"] = False

    resp = sb.table("boat_profiles").insert(row).execute()
    return resp.data[0]


@router.put("/{boat_id}", response_model=BoatOut)
def update_boat(
    boat_id: str,
    body: BoatUpdate,
    user_id: str = Depends(get_current_user),
):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    resp = (
        sb.table("boat_profiles")
        .update(updates)
        .eq("id", boat_id)
        .eq("user_id", user_id)
        .eq("is_preset", False)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Boat not found or not yours")
    return resp.data[0]


@router.delete("/{boat_id}", status_code=204)
def delete_boat(boat_id: str, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = (
        sb.table("boat_profiles")
        .delete()
        .eq("id", boat_id)
        .eq("user_id", user_id)
        .eq("is_preset", False)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Boat not found or not yours")
    return None
