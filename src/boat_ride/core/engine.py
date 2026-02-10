from __future__ import annotations

from boat_ride.core.models import TripPlan, RideScore
from boat_ride.providers.base import EnvProvider
from boat_ride.core.scoring import score_point


def run_engine(plan: TripPlan, provider: EnvProvider) -> list[RideScore]:
    env_series = provider.get_env_series(plan)
    scores = [score_point(plan.boat, env) for env in env_series]
    return scores
