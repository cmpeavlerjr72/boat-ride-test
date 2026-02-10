from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import radians, sin, cos, asin, sqrt
from typing import Any, Dict, List, Optional, Tuple

import requests

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.base import EnvProvider


def _parse_local(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # great-circle distance (nautical miles)
    R_km = 6371.0
    lat1r, lon1r, lat2r, lon2r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = sin(dlat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    km = R_km * c
    return km * 0.539957


def _linear_interp(ts: List[datetime], vs: List[float], t: datetime) -> Optional[float]:
    if not ts or not vs or len(ts) != len(vs):
        return None
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]

    # find bracketing interval (simple scan; lists are small-ish)
    for i in range(1, len(ts)):
        if ts[i] >= t:
            t0, t1 = ts[i - 1], ts[i]
            v0, v1 = vs[i - 1], vs[i]
            dt = (t1 - t0).total_seconds()
            if dt <= 0:
                return v0
            w = (t - t0).total_seconds() / dt
            return v0 + w * (v1 - v0)
    return vs[-1]


def _central_diff_per_hr(ts: List[datetime], vs: List[float], t: datetime) -> Optional[float]:
    """
    Approx tide rate (ft/hr) using a small +/- window around t.
    """
    if len(ts) < 3:
        return None

    # find nearest index
    idx = min(range(len(ts)), key=lambda i: abs((ts[i] - t).total_seconds()))
    i0 = max(0, idx - 1)
    i1 = min(len(ts) - 1, idx + 1)
    if i1 == i0:
        return None

    dt_hr = (ts[i1] - ts[i0]).total_seconds() / 3600.0
    if dt_hr == 0:
        return None
    return (vs[i1] - vs[i0]) / dt_hr


@dataclass
class CoopStation:
    id: str
    name: str
    lat: float
    lon: float


@dataclass
class COOPSTideProvider(EnvProvider):
    """
    Tide layer (Phase 1):
      - Finds nearest NOAA CO-OPS station (unless station_id is supplied)
      - Fetches tide predictions (ft) for the trip window
      - Interpolates to each sample time
      - Emits tide_ft plus helpful tide metadata in env.meta

    NOTE:
      - This is *tide height*, not depth. Depth integration comes later.
      - Currents are not included yet (CO-OPS has currents at some PORTS stations,
        but they’re a separate surface-current product/API shape).
    """

    # If provided, use this station always; otherwise choose nearest to each route point (or trip centroid)
    station_id: Optional[str] = None

    # CO-OPS settings
    datum: str = "MLLW"
    units: str = "english"   # english = feet
    timezone: str = "lst_ldt" # local standard/daylight
    interval: str = "6"      # 6-minute predictions
    product: str = "predictions"  # tide predictions

    # How far outside the trip window to fetch (helps interpolation near edges)
    padding_hours: int = 6

    def __post_init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(
            {
                "User-Agent": "BoatRidePOC/0.0.1",
                "Accept": "application/json",
            }
        )
        self._stations: Optional[List[CoopStation]] = None
        self._tide_cache: Dict[str, Tuple[List[datetime], List[float], Dict[str, Any]]] = {}

    # ---------- Station discovery ----------

    def _load_stations(self) -> List[CoopStation]:
        if self._stations is not None:
            return self._stations

        # NOAA CO-OPS stations list (MDAPI)
        # Returns JSON with stations including lat/lng and id.
        url = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
        r = self.s.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

        out: List[CoopStation] = []
        for st in data.get("stations", []) or []:
            try:
                sid = str(st.get("id"))
                name = str(st.get("name", sid))
                lat = float(st.get("lat"))
                lon = float(st.get("lng"))
                out.append(CoopStation(id=sid, name=name, lat=lat, lon=lon))
            except Exception:
                continue

        self._stations = out
        return out

    def _nearest_station(self, lat: float, lon: float) -> Tuple[Optional[CoopStation], Optional[float]]:
        sts = self._load_stations()
        if not sts:
            return None, None
        best = min(sts, key=lambda s: _haversine_nm(lat, lon, s.lat, s.lon))
        dist = _haversine_nm(lat, lon, best.lat, best.lon)
        return best, dist

    # ---------- Tide fetch ----------

    def _fetch_tides(self, station_id: str, begin: datetime, end: datetime) -> Tuple[List[datetime], List[float], Dict[str, Any]]:
        """
        Fetch reminded tide predictions from CO-OPS Data API.
        """
        cache_key = f"{station_id}:{begin.strftime('%Y%m%d%H%M')}:{end.strftime('%Y%m%d%H%M')}:{self.product}:{self.datum}:{self.units}:{self.timezone}:{self.interval}"
        if cache_key in self._tide_cache:
            return self._tide_cache[cache_key]

        # CO-OPS Data API endpoint
        url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
        params = {
            "format": "json",
            "product": self.product,
            "station": station_id,
            "begin_date": begin.strftime("%Y%m%d %H:%M"),
            "end_date": end.strftime("%Y%m%d %H:%M"),
            "datum": self.datum,
            "units": self.units,
            "time_zone": self.timezone,
            "interval": self.interval,
        }

        r = self.s.get(url, params=params, timeout=40)
        r.raise_for_status()
        data = r.json()

        # Data shape depends on product; for predictions it’s usually {"predictions":[{"t":"...","v":"..."}]}
        rows = data.get("predictions") or data.get("data") or []
        ts: List[datetime] = []
        vs: List[float] = []

        for row in rows:
            try:
                tstr = row.get("t")
                vstr = row.get("v")
                if tstr is None or vstr is None:
                    continue
                # CO-OPS returns local timestamps if time_zone=lst_ldt; format often "YYYY-MM-DD HH:MM"
                t = datetime.strptime(tstr, "%Y-%m-%d %H:%M")
                v = float(vstr)
                ts.append(t)
                vs.append(v)
            except Exception:
                continue

        meta = {
            "coops_station": station_id,
            "coops_product": self.product,
            "coops_datum": self.datum,
            "coops_units": self.units,
            "coops_tz": self.timezone,
            "coops_interval": self.interval,
            "coops_begin": begin.strftime("%Y-%m-%d %H:%M"),
            "coops_end": end.strftime("%Y-%m-%d %H:%M"),
            "coops_rows": len(ts),
        }

        self._tide_cache[cache_key] = (ts, vs, meta)
        return ts, vs, meta

    # ---------- Provider output ----------

    def get_env_series(self, plan: TripPlan) -> List[EnvAtPoint]:
        start = _parse_local(plan.start_time_local) - timedelta(hours=self.padding_hours)
        end = _parse_local(plan.end_time_local) + timedelta(hours=self.padding_hours)
        step = timedelta(minutes=plan.sample_every_minutes)

        # If the trip has a fixed station, use it. Otherwise, choose a station per point.
        # (Phase 1 simplification: pick station by trip centroid so tide is consistent along route.)
        route = plan.route or []
        if route:
            lat0 = sum(p.lat for p in route) / len(route)
            lon0 = sum(p.lon for p in route) / len(route)
        else:
            lat0, lon0 = 0.0, 0.0

        station_meta: Dict[str, Any] = {}
        if self.station_id:
            station = CoopStation(id=str(self.station_id), name=str(self.station_id), lat=lat0, lon=lon0)
            station_dist = None
        else:
            station, station_dist = self._nearest_station(lat0, lon0)

        ts: List[datetime] = []
        vs: List[float] = []
        fetch_meta: Dict[str, Any] = {}

        if station is not None:
            station_meta = {
                "coops_station_id": station.id,
                "coops_station_name": station.name,
                "coops_station_distance_nm": station_dist,
            }
            try:
                ts, vs, fetch_meta = self._fetch_tides(station.id, start, end)
            except Exception as e:
                fetch_meta = {"coops_error": f"{type(e).__name__}: {e}"}
        else:
            fetch_meta = {"coops_error": "No CO-OPS stations available"}

        out: List[EnvAtPoint] = []
        t = _parse_local(plan.start_time_local)
        idx = 0
        npts = max(1, len(plan.route))

        while t <= _parse_local(plan.end_time_local):
            p = plan.route[min(idx, npts - 1)]

            tide_ft = _linear_interp(ts, vs, t) if ts and vs else None
            tide_rate = _central_diff_per_hr(ts, vs, t) if ts and vs else None
            tide_phase = None
            if tide_rate is not None:
                if tide_rate > 0.05:
                    tide_phase = "flood"
                elif tide_rate < -0.05:
                    tide_phase = "ebb"
                else:
                    tide_phase = "slack"

            meta: Dict[str, Any] = {}
            meta.update(station_meta)
            meta.update(fetch_meta)
            meta["tide_source"] = "coops"
            meta["tide_rate_ft_per_hr"] = tide_rate
            meta["tide_phase"] = tide_phase

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
                    tide_ft=tide_ft,
                    current_kt=None,
                    current_dir_deg=None,
                    meta=meta,
                )
            )

            t += step
            idx += 1

        return out
