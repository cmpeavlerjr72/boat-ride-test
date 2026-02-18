"""FastAPI REST backend for the boat-ride scoring engine."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from boat_ride.auth import get_optional_user
from boat_ride.core.engine import run_engine
from boat_ride.core.models import BoatProfile, RideScore, ScoringPreferences, TripPlan
from boat_ride.db import get_supabase
from boat_ride.providers.combined import build_provider
from boat_ride.routers import boats, profiles, reports, routes, scoring_feedback

log = logging.getLogger(__name__)

app = FastAPI(title="Boat Ride", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------
app.include_router(profiles.router)
app.include_router(boats.router)
app.include_router(routes.router)
app.include_router(reports.router)
app.include_router(scoring_feedback.router)


# ---------------------------------------------------------------------------
# Module-level provider singletons (L1 caches persist across requests)
# ---------------------------------------------------------------------------
_provider_cache: Dict[str, Any] = {}


def _get_provider(provider_str: str):
    if provider_str not in _provider_cache:
        _provider_cache[provider_str] = build_provider(provider_str)
    return _provider_cache[provider_str]


# ---------------------------------------------------------------------------
# Area tracking — record route bounding boxes for the background worker
# ---------------------------------------------------------------------------

def _record_active_area(route_points: list) -> None:
    """Write route bounding box to Redis sorted set so the worker knows
    which areas are actively queried by users."""
    try:
        from boat_ride.cache.redis_client import get_redis
        from boat_ride.cache.keys import worker_active_areas

        r = get_redis()
        if r is None:
            return

        lats = [rp.lat for rp in route_points]
        lons = [rp.lon for rp in route_points]
        area_key = f"{min(lats):.2f},{min(lons):.2f},{max(lats):.2f},{max(lons):.2f}"
        # Score = current unix time so the worker can expire stale areas
        r.zadd(worker_active_areas(), {area_key: time.time()})
    except Exception:
        pass


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
    water_type: str = "auto"  # "auto" | "lake" | "tidal"


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
    water_type_used: str = "tidal"  # "lake" | "tidal"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    redis_ok = False
    try:
        from boat_ride.cache.redis_client import get_redis
        r = get_redis()
        if r is not None:
            r.ping()
            redis_ok = True
    except Exception:
        pass

    supabase_ok = get_supabase() is not None

    return {"status": "ok", "redis": redis_ok, "supabase": supabase_ok}


def _load_user_prefs(user_id: Optional[str]) -> Optional[ScoringPreferences]:
    """Load scoring preferences for an authenticated user, or return None."""
    if not user_id:
        return None
    try:
        sb = get_supabase()
        if sb is None:
            return None
        resp = (
            sb.table("scoring_preferences")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            return ScoringPreferences(
                wind_multiplier=row.get("wind_multiplier", 1.0),
                wave_multiplier=row.get("wave_multiplier", 1.0),
                period_multiplier=row.get("period_multiplier", 1.0),
                chop_multiplier=row.get("chop_multiplier", 1.0),
                precip_multiplier=row.get("precip_multiplier", 1.0),
                tide_multiplier=row.get("tide_multiplier", 1.0),
                overall_offset=row.get("overall_offset", 0.0),
            )
    except Exception:
        pass
    return None


def _resolve_water_type(
    water_type: str, provider_str: str, route: List[RoutePointIn]
) -> tuple:
    """Resolve water_type into a (provider_str, water_type_used) tuple.

    - "lake": strip coops/tide tokens from provider string
    - "tidal": keep provider string as-is
    - "auto": check distance to nearest CO-OPS station; >25 nm → lake
    """
    wt = water_type.lower().strip()

    if wt == "lake":
        tokens = [t for t in provider_str.split("+") if t.strip().lower() not in ("coops", "tide")]
        return "+".join(tokens) or provider_str, "lake"

    if wt == "tidal":
        return provider_str, "tidal"

    # auto-detect using CO-OPS station proximity
    if route:
        lat0 = sum(rp.lat for rp in route) / len(route)
        lon0 = sum(rp.lon for rp in route) / len(route)
    else:
        return provider_str, "tidal"

    try:
        from boat_ride.providers.coops import COOPSTideProvider
        coops = COOPSTideProvider()
        _station, dist_nm = coops._nearest_station(lat0, lon0)
        if _station is None or (dist_nm is not None and dist_nm > 25):
            tokens = [t for t in provider_str.split("+") if t.strip().lower() not in ("coops", "tide")]
            return "+".join(tokens) or provider_str, "lake"
    except Exception:
        pass

    return provider_str, "tidal"


@app.post("/score-route", response_model=ScoreRouteResponse)
def score_route(
    req: ScoreRouteRequest,
    user_id: Optional[str] = Depends(get_optional_user),
):
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

        # Load personalized scoring preferences if user is authenticated
        prefs = _load_user_prefs(user_id)

        resolved_provider_str, water_type_used = _resolve_water_type(
            req.water_type, req.provider, req.route
        )
        provider = _get_provider(resolved_provider_str)
        raw_scores: list[RideScore] = run_engine(plan, provider, prefs=prefs)
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

        # Record this area for the background worker (fire-and-forget)
        _record_active_area(req.route)

        return ScoreRouteResponse(scores=scores, water_type_used=water_type_used)

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
