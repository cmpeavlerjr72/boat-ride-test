from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from boat_ride.core.models import TripPlan, EnvAtPoint
from math import atan2, cos, radians, sin, degrees


def _parse_local(dt_str: str, tz_name: Optional[str] = None) -> datetime:
    from boat_ride.core.models import _parse_local as _pl
    return _pl(dt_str, tz_name)


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

    When a FetchCalculator is available, dynamically computes fetch from coastline
    geometry. Manual route_point.fetch_nm values are still honored as overrides.

    IMPORTANT: This provider must emit the same number of samples as NWS/NDBC:
      one EnvAtPoint per time step from start..end, cycling through plan.route.
    """

    default_fetch_nm: float = 1.0
    _calculator: Any = field(default=None, repr=False)
    _fetch_cache: Dict[str, Any] = field(default_factory=dict, repr=False)

    def _get_calculator(self):
        if self._calculator is None:
            try:
                from boat_ride.geo.fetch_calculator import FetchCalculator
                self._calculator = FetchCalculator()
            except Exception:
                self._calculator = False  # sentinel: don't retry
        return self._calculator if self._calculator is not False else None

    def _precompute_fetch(self, plan: TripPlan) -> None:
        """Compute dynamic fetch for all route points lacking manual fetch_nm."""
        calc = self._get_calculator()
        if calc is None:
            return

        points_to_compute = []
        indices = []
        for i, rp in enumerate(plan.route):
            if rp.fetch_nm is None:
                points_to_compute.append((rp.lat, rp.lon))
                indices.append(i)

        if not points_to_compute:
            return

        results = calc.compute_fetch_batch(points_to_compute)
        for idx, result in zip(indices, results):
            cache_key = f"{plan.route[idx].lat:.6f},{plan.route[idx].lon:.6f}"
            self._fetch_cache[cache_key] = result

    def _get_fetch_nm(self, route_point, plan: Optional[TripPlan] = None) -> float:
        # Manual override takes priority
        v = getattr(route_point, "fetch_nm", None)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass

        # Try dynamic fetch from cache
        cache_key = f"{route_point.lat:.6f},{route_point.lon:.6f}"
        result = self._fetch_cache.get(cache_key)
        if result is not None:
            # Use the average of min and max as the default fetch
            return (result.min_fetch_nm + result.max_fetch_nm) / 2.0

        return float(self.default_fetch_nm)

    def _get_fetch_result(self, route_point) -> Optional[Any]:
        """Get the full FetchResult for a route point, if dynamically computed."""
        cache_key = f"{route_point.lat:.6f},{route_point.lon:.6f}"
        return self._fetch_cache.get(cache_key)

    def get_env_series(self, plan: TripPlan) -> List[EnvAtPoint]:
        # Precompute dynamic fetch for points without manual values
        self._precompute_fetch(plan)

        times = plan.sample_times
        out: List[EnvAtPoint] = []
        npts = max(1, len(plan.route))

        for idx, t in enumerate(times):
            p = plan.route[min(idx, npts - 1)]

            # Route heading
            if npts >= 2:
                if idx < npts - 1:
                    p_next = plan.route[idx + 1]
                    route_heading_deg = _bearing_deg(p.lat, p.lon, p_next.lat, p_next.lon)
                else:
                    p_prev = plan.route[npts - 2]
                    route_heading_deg = _bearing_deg(p_prev.lat, p_prev.lon, p.lat, p.lon)
            else:
                route_heading_deg = 0.0

            fetch_nm = self._get_fetch_nm(p, plan)
            fetch_result = self._get_fetch_result(p)
            depth_m = getattr(p, "depth_m", None)

            # Auto-detect waterway from fetch result if available
            waterway = getattr(p, "waterway", None)
            if waterway is None and fetch_result is not None:
                waterway = fetch_result.waterway

            meta: Dict[str, Any] = {
                "fetch_nm": fetch_nm,
                "depth_m": depth_m,
                "route_heading_deg": route_heading_deg,
            }

            if waterway is not None:
                meta["waterway"] = waterway

            if fetch_result is not None:
                meta["_fetch_result"] = fetch_result
                meta["fetch_min_nm"] = fetch_result.min_fetch_nm
                meta["fetch_max_nm"] = fetch_result.max_fetch_nm
                meta["fetch_source"] = "dynamic_coastline"
            else:
                meta["fetch_source"] = "manual" if getattr(p, "fetch_nm", None) is not None else "default"

            out.append(
                EnvAtPoint(
                    t_local=t.strftime("%Y-%m-%d %H:%M") if hasattr(t, 'strftime') else str(t),
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
                    meta=meta,
                )
            )

        return out
