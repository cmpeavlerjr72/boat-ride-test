from __future__ import annotations

from abc import ABC, abstractmethod
from boat_ride.core.models import TripPlan, EnvAtPoint


class EnvProvider(ABC):
    """Fetch metocean conditions for each sampled point/time."""

    @abstractmethod
    def get_env_series(self, plan: TripPlan) -> list[EnvAtPoint]:
        raise NotImplementedError
