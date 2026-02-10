from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.http import HTTPClient


def _parse_local(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")


@dataclass
class USACEProvider:
    """
    USACE river gauges / flow / stage (where accessible).
    Safe stub that won't crash.
    """

    user_agent: str = "boat-ride-poc (contact: you@example.com)"

    def __post_init__(self) -> None:
        self.http = HTTPClient(user_agent=self.user_agent)

    def get_env_series(self, plan: TripPlan) -> List[EnvAtPoint]:
        start = _parse_local(plan.start_time_local)
        end = _parse_local(plan.end_time_local)
        step = timedelta(minutes=plan.sample_every_minutes)

        out: List[EnvAtPoint] = []
        t = start
        idx = 0
        npts = max(1, len(plan.route))

        while t <= end:
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
            t += step
            idx += 1

        return out
