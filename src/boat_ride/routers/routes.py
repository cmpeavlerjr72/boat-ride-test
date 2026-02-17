"""Saved routes CRUD."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from boat_ride.auth import get_current_user
from boat_ride.db import get_supabase

router = APIRouter(prefix="/routes", tags=["routes"])


class RoutePointData(BaseModel):
    lat: float
    lon: float
    name: Optional[str] = None


class RouteOut(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    route_points: List[Dict[str, Any]]
    region: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RouteCreate(BaseModel):
    name: str
    description: Optional[str] = None
    route_points: List[RoutePointData] = Field(..., min_length=1)
    region: Optional[str] = None


class RouteUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    route_points: Optional[List[RoutePointData]] = None
    region: Optional[str] = None


@router.get("", response_model=List[RouteOut])
def list_routes(user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = (
        sb.table("saved_routes")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return resp.data


@router.post("", response_model=RouteOut, status_code=201)
def create_route(body: RouteCreate, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    row = {
        "user_id": user_id,
        "name": body.name,
        "description": body.description,
        "route_points": [rp.model_dump() for rp in body.route_points],
        "region": body.region,
    }
    resp = sb.table("saved_routes").insert(row).execute()
    return resp.data[0]


@router.put("/{route_id}", response_model=RouteOut)
def update_route(
    route_id: str,
    body: RouteUpdate,
    user_id: str = Depends(get_current_user),
):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.route_points is not None:
        updates["route_points"] = [rp.model_dump() for rp in body.route_points]
    if body.region is not None:
        updates["region"] = body.region

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    resp = (
        sb.table("saved_routes")
        .update(updates)
        .eq("id", route_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Route not found or not yours")
    return resp.data[0]


@router.delete("/{route_id}", status_code=204)
def delete_route(route_id: str, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = (
        sb.table("saved_routes")
        .delete()
        .eq("id", route_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Route not found or not yours")
    return None
