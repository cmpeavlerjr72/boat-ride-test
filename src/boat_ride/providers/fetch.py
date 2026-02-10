from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from boat_ride.core.models import TripPlan, EnvAtPoint
from math import atan2, cos, radians, sin, degrees


def _parse_local(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # initial bearing, degrees clockwise from north
    lat1r, lon1r, lat2r, lon2r = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2r - lon1r
    x = sin(dlon) * cos(lat2r)
    y = cos(lat1r) * sin(lat2r) - sin(lat1r) * cos(lat2r) * cos(dlon)
    brng = (degrees(atan2(x, y)) + 360.0) % 360.0
    return float(brng)


@dataclass
class FetchChopProvider:
    """
    Provides per-sample fetch_nm (in nautical miles) so the chain can:
      - synthesize inland chop from wind + fetch_nm
      - gate/suppress offshore buoy waves when fetch is small and buoy is far

    IMPORTANT: This provider must emit the same number of samples as NWS/NDBC:
      one EnvAtPoint per time step from start..end, cycling through plan.route.
    """

    default_fetch_nm: float = 1.0

    def _get_fetch_nm(self, route_point) -> float:
        v = getattr(route_point, "fetch_nm", None)
        if v is None:
            return float(self.default_fetch_nm)
        try:
            return float(v)
        except Exception:
            return float(self.default_fetch_nm)

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

            # Route heading: use forward segment normally; for the final clamped points,
            # use the last real segment (prev -> last) so heading doesn't collapse to 0°.
            if npts >= 2:
                if idx < npts - 1:
                    p_next = plan.route[idx + 1]
                    route_heading_deg = _bearing_deg(p.lat, p.lon, p_next.lat, p_next.lon)
                else:
                    p_prev = plan.route[npts - 2]
                    route_heading_deg = _bearing_deg(p_prev.lat, p_prev.lon, p.lat, p.lon)
            else:
                route_heading_deg = 0.0

            fetch_nm = self._get_fetch_nm(p)

            depth_m = getattr(p, "depth_m", None)

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
                    meta={
                        "fetch_nm": fetch_nm,
                        "depth_m": depth_m,
                        "route_heading_deg": route_heading_deg
                    },
                )
            )

            t += step
            idx += 1

        return out
