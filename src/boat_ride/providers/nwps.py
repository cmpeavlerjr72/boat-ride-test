from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.http import HTTPClient


def _parse_local(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")


@dataclass
class NWPSProvider:
    """
    Nearshore Wave Prediction System (NWPS) – gridded nearshore waves.
    Not wired yet: this implementation is a safe stub that will not crash.
    """

    user_agent: str = "boat-ride-poc (contact: you@example.com)"

    def __post_init__(self) -> None:
        self.http = HTTPClient(user_agent=self.user_agent)

    def _lookup_nwps_endpoint(self, lat: float, lon: float) -> Optional[str]:
        # TODO: region selection
        return None

    def _query_grid(self, endpoint: str, lat: float, lon: float, t_local: str) -> Dict[str, Any]:
        # TODO: real NWPS query + extraction
        raise NotImplementedError("NWPSProvider not wired yet")

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

            endpoint = self._lookup_nwps_endpoint(p.lat, p.lon)
            meta: Dict[str, Any] = {"waves_source": "nwps", "nwps_endpoint": endpoint}

            wave_height_ft = wave_period_s = wave_dir_deg = None

            if endpoint:
                try:
                    data = self._query_grid(endpoint, p.lat, p.lon, t.strftime("%Y-%m-%d %H:%M"))
                    wave_height_ft = data.get("wave_height_ft")
                    wave_period_s = data.get("wave_period_s")
                    wave_dir_deg = data.get("wave_dir_deg")
                    meta["nwps_time"] = data.get("source_time")
                except Exception as e:
                    meta["nwps_error"] = f"{type(e).__name__}: {e}"

            out.append(
                EnvAtPoint(
                    t_local=t.strftime("%Y-%m-%d %H:%M"),
                    lat=p.lat,
                    lon=p.lon,
                    wind_speed_kt=None,
                    wind_gust_kt=None,
                    wind_dir_deg=None,
                    precip_prob=None,
                    wave_height_ft=wave_height_ft,
                    wave_period_s=wave_period_s,
                    wave_dir_deg=wave_dir_deg,
                    tide_ft=None,
                    current_kt=None,
                    current_dir_deg=None,
                    meta=meta,
                )
            )

            t += step
            idx += 1

        return out
