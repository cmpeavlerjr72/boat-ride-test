"""FastAPI REST backend for the boat-ride scoring engine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from boat_ride.core.engine import run_engine
from boat_ride.core.models import BoatProfile, RideScore, TripPlan
from boat_ride.providers.combined import build_provider

app = FastAPI(title="Boat Ride", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RoutePointIn(BaseModel):
    lat: float
    lon: float
    name: Optional[str] = None
    fetch_nm: Optional[float] = None
    waterway: Optional[str] = None


class ScoreRouteRequest(BaseModel):
    route: List[RoutePointIn] = Field(..., min_length=1)
    start_time: str = Field(..., description="Local start time, e.g. '2026-01-22 08:00'")
    end_time: str = Field(..., description="Local end time, e.g. '2026-01-22 12:00'")
    timezone: str = "America/New_York"
    sample_every_minutes: int = 20
    boat: Optional[BoatProfile] = None
    provider: str = "nws+ndbc+fetch+coops"


class ScoreOut(BaseModel):
    t_local: str
    lat: float
    lon: float
    score_0_100: float
    label: str
    reasons: List[str] = []
    detail: Dict[str, Any] = {}


class ScoreRouteResponse(BaseModel):
    scores: List[ScoreOut]
    trip_id: str = "api"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/score-route", response_model=ScoreRouteResponse)
def score_route(req: ScoreRouteRequest):
    try:
        plan = TripPlan(
            trip_id="api",
            boat=req.boat or BoatProfile(),
            route=[rp.model_dump() for rp in req.route],
            start_time_local=req.start_time,
            end_time_local=req.end_time,
            sample_every_minutes=req.sample_every_minutes,
            timezone=req.timezone,
        )

        provider = build_provider(req.provider)
        raw_scores: list[RideScore] = run_engine(plan, provider)
        raw_scores.sort(key=lambda s: s.t_local)

        scores = [
            ScoreOut(
                t_local=s.t_local,
                lat=s.lat,
                lon=s.lon,
                score_0_100=s.score_0_100,
                label=s.label,
                reasons=s.reasons,
                detail=_sanitize_detail(s.detail),
            )
            for s in raw_scores
        ]

        return ScoreRouteResponse(scores=scores)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sanitize_detail(detail: dict) -> dict:
    """Remove non-serializable objects (like FetchResult) from detail dict."""
    out = {}
    for k, v in detail.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            v = _sanitize_detail(v)
        try:
            # Quick JSON-serialization check
            import json
            json.dumps(v)
            out[k] = v
        except (TypeError, ValueError):
            out[k] = str(v)
    return out
