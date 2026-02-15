from __future__ import annotations

from dataclasses import dataclass
from typing import List

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.http import HTTPClient


@dataclass
class USACEProvider:
    """
    USACE river gauges / flow / stage (where accessible).

    TODO: Wire up real USACE data. The eventual implementation should:
      - Query USACE RiverGages API or CWMS for nearby gauges
      - Fetch stage (ft), discharge (cfs), and flow velocity if available
      - Provide river current estimates useful for inland route scoring
    Currently a safe stub that returns empty environmental fields without crashing.
    """

    user_agent: str = "boat-ride-poc (contact: you@example.com)"

    def __post_init__(self) -> None:
        self.http = HTTPClient(user_agent=self.user_agent)

    def get_env_series(self, plan: TripPlan) -> List[EnvAtPoint]:
        times = plan.sample_times
        out: List[EnvAtPoint] = []
        npts = max(1, len(plan.route))

        for idx, t in enumerate(times):
            p = plan.route[min(idx, npts - 1)]
            out.append(
                EnvAtPoint(
                    t_local=t.strftime("%Y-%m-%d %H:%M"),
                    lat=p.lat,
                    lon=p.lon,
                    wind_speed_kt=None,
                    wind_gust_kt=None,
                    wind_dir_deg=None,
                    precip_prob=None,
                    wave_height_ft=None,
                    wave_period_s=None,
                    wave_dir_deg=None,
                    tide_ft=None,
                    current_kt=None,
                    current_dir_deg=None,
                    meta={"water_source": "usace", "usace_note": "not wired yet"},
                )
            )

        return out
