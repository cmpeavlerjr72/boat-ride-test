from __future__ import annotations

from typing import Optional

from boat_ride.core.models import TripPlan, RideScore, ScoringPreferences
from boat_ride.core.route import normalize_route
from boat_ride.providers.base import EnvProvider
from boat_ride.core.scoring import score_point


def run_engine(
    plan: TripPlan,
    provider: EnvProvider,
    prefs: Optional[ScoringPreferences] = None,
) -> list[RideScore]:
    # Compute and attach a normalized route before providers run
    if plan._normalized_route is None:
        raw_pts = [{"lat": p.lat, "lon": p.lon, "waterway": p.waterway} for p in plan.route]
        plan._normalized_route = normalize_route(raw_pts, route_id=plan.trip_id)

    env_series = provider.get_env_series(plan)
    scores = [score_point(plan.boat, env, prefs=prefs) for env in env_series]
    return scores
