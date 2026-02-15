from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, PrivateAttr


def _parse_local(dt_str: str, tz_name: Optional[str] = None) -> datetime:
    """Parse a local time string, optionally attaching a timezone.

    When *tz_name* is provided (e.g. ``"America/New_York"``), the returned
    datetime is timezone-aware.  Otherwise it is naive (POC compat).
    """
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    if tz_name:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt


class BoatProfile(BaseModel):
    name: str = "My Boat"
    length_ft: float = 22
    beam_ft: float = 8.5
    draft_ft: float = 1.5

    # Very POC-y: these let us turn “conditions” into “ride quality”
    comfort_bias: float = Field(default=0.0, description="-1..+1 (more tolerant -> +)")
    max_safe_wind_kt: float = 25
    max_safe_wave_ft: float = 4.0


class RoutePoint(BaseModel):
    lat: float
    lon: float
    name: Optional[str] = None

    # Inland helper: used only when wave data is missing
    fetch_nm: Optional[float] = None

    # "inland" / "coastal" / "offshore" (optional)
    waterway: Optional[str] = None


class TripPlan(BaseModel):
    trip_id: str = "sample"
    boat: BoatProfile
    route: List[RoutePoint]

    # ISO-like strings for POC (we can switch to aware datetimes later)
    start_time_local: str  # e.g. "2026-01-22 08:00"
    end_time_local: str    # e.g. "2026-01-22 12:00"
    sample_every_minutes: int = 15

    # Simple speed assumption for POC
    cruise_speed_kt: float = 18.0

    # Optional context (helps inland logic)
    timezone: str = "America/New_York"
    default_fetch_nm: float = 1.0

    # Computed normalized route (attached by engine before running providers)
    _normalized_route: Any = PrivateAttr(default=None)

    # ---- Compatibility properties (fixes your NWPS/COOPS/fetch errors) ----
    @property
    def route_points(self) -> List[RoutePoint]:
        return self.route

    @property
    def sample_times(self) -> List[datetime]:
        start = _parse_local(self.start_time_local, self.timezone)
        end = _parse_local(self.end_time_local, self.timezone)
        step = timedelta(minutes=self.sample_every_minutes)
        out: List[datetime] = []
        t = start
        while t <= end:
            out.append(t)
            t += step
        return out

    # ---- Route sampling: map each sample time to a position along the route ----
    def iter_sample_positions(self) -> List[Tuple[datetime, float, float, Dict[str, Any]]]:
        """
        Returns [(t, lat, lon, meta), ...] at each sample time.

        We linearly interpolate along route points by elapsed fraction of trip duration.
        This is a POC stand-in for “follow the channel polyline / route geometry”.
        """
        times = self.sample_times
        if not times:
            return []

        if len(self.route) == 1:
            p = self.route[0]
            return [(t, p.lat, p.lon, {"route_name": p.name, "fetch_nm": p.fetch_nm}) for t in times]

        start_t = times[0]
        end_t = times[-1]
        total_s = max(1.0, (end_t - start_t).total_seconds())

        nseg = len(self.route) - 1
        out: List[Tuple[datetime, float, float, Dict[str, Any]]] = []

        for t in times:
            frac = (t - start_t).total_seconds() / total_s
            frac = min(1.0, max(0.0, frac))

            pos = frac * nseg
            i = min(nseg - 1, int(pos))
            u = pos - i  # 0..1 within segment

            a = self.route[i]
            b = self.route[i + 1]

            lat = a.lat + u * (b.lat - a.lat)
            lon = a.lon + u * (b.lon - a.lon)

            # Interpolate fetch if provided; else fall back to defaults
            fetch_a = a.fetch_nm if a.fetch_nm is not None else self.default_fetch_nm
            fetch_b = b.fetch_nm if b.fetch_nm is not None else self.default_fetch_nm
            fetch_nm = fetch_a + u * (fetch_b - fetch_a)

            meta = {
                "route_seg_index": i,
                "route_from": a.name,
                "route_to": b.name,
                "fetch_nm": fetch_nm,
                "waterway": a.waterway or b.waterway,
            }
            out.append((t, lat, lon, meta))

        return out


class EnvAtPoint(BaseModel):
    t_local: str
    lat: float
    lon: float

    # weather (from NWS)
    wind_speed_kt: Optional[float] = None
    wind_gust_kt: Optional[float] = None
    wind_dir_deg: Optional[float] = None

    # marine (may be missing initially)
    wave_height_ft: Optional[float] = None
    wave_period_s: Optional[float] = None
    wave_dir_deg: Optional[float] = None

    precip_prob: Optional[float] = None  # 0..1

    tide_ft: Optional[float] = None
    current_kt: Optional[float] = None
    current_dir_deg: Optional[float] = None

    meta: Dict[str, Any] = Field(default_factory=dict)


class RideScore(BaseModel):
    t_local: str
    lat: float
    lon: float
    score_0_100: float
    label: Literal["great", "ok", "rough", "avoid"]
    reasons: List[str] = []
    detail: dict = {}
