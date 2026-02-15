from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.http import HTTPClient


@dataclass
class NWPSProvider:
    """
    Nearshore Wave Prediction System (NWPS) – gridded nearshore waves.

    TODO: Wire up real NWPS data. NWPS provides high-resolution nearshore wave
    forecasts from NOAA/NWS WFOs. The eventual implementation should:
      - Resolve the correct WFO / NWPS region from lat/lon
      - Fetch the relevant GRIB2 or OPeNDAP slice for (Hs, Tp, Dir)
      - Interpolate to route points and sample times
    Currently a safe stub that returns empty wave fields without crashing.
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
        times = plan.sample_times
        out: List[EnvAtPoint] = []
        npts = max(1, len(plan.route))

        for idx, t in enumerate(times):
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

        return out
