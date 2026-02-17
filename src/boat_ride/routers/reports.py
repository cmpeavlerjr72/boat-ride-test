"""Crowdsource reports: create, nearby spatial query, confirm, delete."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from boat_ride.auth import get_current_user
from boat_ride.db import get_supabase

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportCreate(BaseModel):
    report_type: str = Field(..., pattern="^(ride_quality|traffic|sandbar)$")
    lat: float
    lon: float
    data: Dict[str, Any] = Field(default_factory=dict)


class ReportOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    report_type: str
    lat: float
    lon: float
    data: Dict[str, Any] = {}
    confirmation_count: int = 0
    is_stale: Optional[bool] = None
    distance_nm: Optional[float] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None


class ConfirmOut(BaseModel):
    report_id: str
    confirmation_count: int


@router.post("", response_model=ReportOut, status_code=201)
def create_report(body: ReportCreate, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = sb.rpc("create_report", {
        "p_user_id": user_id,
        "p_report_type": body.report_type,
        "p_lat": body.lat,
        "p_lon": body.lon,
        "p_data": body.data,
    }).execute()

    report_id = resp.data
    if not report_id:
        raise HTTPException(status_code=500, detail="Failed to create report")

    # Fetch the full row to return
    row = (
        sb.table("crowdsource_reports")
        .select("*")
        .eq("id", report_id)
        .single()
        .execute()
    )
    return row.data


@router.get("/nearby", response_model=List[ReportOut])
def nearby_reports(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_nm: float = Query(default=5.0, ge=0.1, le=50.0),
    types: Optional[str] = Query(default=None, description="Comma-separated: ride_quality,traffic,sandbar"),
    user_id: str = Depends(get_current_user),
):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    type_list = ["ride_quality", "traffic", "sandbar"]
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]

    resp = sb.rpc("nearby_reports", {
        "p_lat": lat,
        "p_lon": lon,
        "p_radius_nm": radius_nm,
        "p_types": type_list,
    }).execute()

    return resp.data or []


@router.post("/{report_id}/confirm", response_model=ConfirmOut)
def confirm_report(report_id: str, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = sb.rpc("confirm_report", {
        "p_report_id": report_id,
        "p_user_id": user_id,
    }).execute()

    count = resp.data if isinstance(resp.data, int) else 0
    return ConfirmOut(report_id=report_id, confirmation_count=count)


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resp = (
        sb.table("crowdsource_reports")
        .delete()
        .eq("id", report_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Report not found or not yours")
    return None
