from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

import requests

import time
from requests.exceptions import ReadTimeout, ConnectionError

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.base import EnvProvider


def _parse_local(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")


def _parse_iso(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


def _kt_from_mps(v: float) -> float:
    return v * 1.943844


def _kt_from_kmh(v: float) -> float:
    return v * 0.539957


def _mph_to_kt(mph: float) -> float:
    return mph * 0.868976


def _parse_wind_speed_to_kt(text: str) -> Optional[float]:
    """
    NWS forecastHourly windSpeed strings:
      "10 mph" or "5 to 10 mph"
    """
    if not text:
        return None
    t = text.lower().replace("mph", "").strip()
    if "to" in t:
        parts = [p.strip() for p in t.split("to", 1)]
        try:
            lo = float(parts[0])
            hi = float(parts[1])
            return float(_mph_to_kt((lo + hi) / 2))
        except Exception:
            return None
    try:
        return float(_mph_to_kt(float(t.split()[0])))
    except Exception:
        return None


def _dir_to_deg(d: Optional[str]) -> Optional[float]:
    if d is None:
        return None
    ds = str(d).strip().upper()
    try:
        return float(ds)
    except Exception:
        pass

    compass = {
        "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
        "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
        "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
        "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
    }
    return compass.get(ds)


@dataclass
class _HourlyPeriod:
    start: datetime
    end: datetime
    wind_speed_kt: Optional[float]
    wind_dir_deg: Optional[float]
    precip_prob: Optional[float]  # 0..1


@dataclass
class _GridSeries:
    # time -> value, but we store as list for nearest lookup
    times: list[datetime]
    values: list[Optional[float]]


class NWSProvider(EnvProvider):
    """
    NWS provider with fallback:

    Primary:
      - /points/{lat},{lon} -> forecastHourly URL
      - forecastHourly -> periods

    Fallback (more reliable):
      - /points/{lat},{lon} -> forecastGridData URL
      - forecastGridData -> numeric time series (windSpeed, windDirection, probabilityOfPrecipitation)
    """

    def __init__(self, user_agent: str = "BoatRidePOC/0.0.1 (contact: you@example.com)"):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept": "application/geo+json"})

        # Cache per (lat,lon)
        self._meta_cache: dict[str, dict] = {}  # key -> properties from /points
        self._hourly_cache: dict[str, list[_HourlyPeriod]] = {}  # forecastHourly url -> periods
        self._grid_cache: dict[str, dict] = {}  # forecastGridData url -> full JSON

    def _get_json(self, url: str, timeout: int = 20, tries: int = 4, backoff_s: float = 0.8) -> dict:
        last_err: Exception | None = None
        for attempt in range(tries):
            try:
                r = self.s.get(url, timeout=timeout)
                r.raise_for_status()
                return r.json()
            except (ReadTimeout, ConnectionError) as e:
                last_err = e
                # exponential backoff: 0.8s, 1.6s, 3.2s...
                time.sleep(backoff_s * (2 ** attempt))
        raise last_err if last_err else RuntimeError("Unknown request failure")


    def _points_properties(self, lat: float, lon: float) -> dict:
        key = f"{lat:.4f},{lon:.4f}"
        if key in self._meta_cache:
            return self._meta_cache[key]

        url = f"https://api.weather.gov/points/{lat},{lon}"
        data = self._get_json(url, timeout=20, tries=4, backoff_s=0.8)

        props = data["properties"]
        self._meta_cache[key] = props
        return props

    # ---------- Hourly forecast path ----------

    def _hourly_periods(self, forecast_hourly_url: str) -> list[_HourlyPeriod]:
        if forecast_hourly_url in self._hourly_cache:
            return self._hourly_cache[forecast_hourly_url]

        # For hourly we want retries too, but still allow caller fallback on HTTP errors like 404
        r = None
        last_err = None
        for attempt in range(4):
            try:
                r = self.s.get(forecast_hourly_url, timeout=20)
                break
            except (ReadTimeout, ConnectionError) as e:
                last_err = e
                time.sleep(0.8 * (2 ** attempt))

        if r is None:
            raise last_err if last_err else RuntimeError("Hourly request failed")

        r.raise_for_status()
        data = r.json()


        periods: list[_HourlyPeriod] = []
        for p in data["properties"]["periods"]:
            start = _parse_iso(p["startTime"])
            end = _parse_iso(p["endTime"])
            ws = _parse_wind_speed_to_kt(p.get("windSpeed", ""))
            wd = _dir_to_deg(p.get("windDirection"))

            pop_val = None
            pop_obj = p.get("probabilityOfPrecipitation")
            if isinstance(pop_obj, dict):
                v = pop_obj.get("value")
                if v is not None:
                    pop_val = float(v) / 100.0

            periods.append(_HourlyPeriod(start, end, ws, wd, pop_val))

        self._hourly_cache[forecast_hourly_url] = periods
        return periods

    def _pick_hourly(self, periods: list[_HourlyPeriod], t_local_naive: datetime) -> Optional[_HourlyPeriod]:
        if not periods:
            return None
        return min(periods, key=lambda p: abs((p.start.replace(tzinfo=None) - t_local_naive).total_seconds()))

    # ---------- Grid data fallback path ----------

    def _grid_json(self, forecast_grid_url: str) -> dict:
        if forecast_grid_url in self._grid_cache:
            return self._grid_cache[forecast_grid_url]
        data = self._get_json(forecast_grid_url, timeout=20, tries=4, backoff_s=0.8)

        self._grid_cache[forecast_grid_url] = data
        return data

    def _parse_valid_time_start(self, valid_time: str) -> Optional[datetime]:
        # validTime like "2026-01-22T14:00:00+00:00/PT1H"
        if not valid_time:
            return None
        start = valid_time.split("/", 1)[0]
        try:
            return _parse_iso(start)
        except Exception:
            return None

    def _series_from_grid(self, grid: dict, path: str) -> _GridSeries:
        """
        path like: ("windSpeed"), ("windDirection"), ("probabilityOfPrecipitation")
        """
        props = grid.get("properties", {})
        node = props.get(path, {})
        unit = node.get("uom") or node.get("unitCode")  # sometimes uom, sometimes unitCode
        values = node.get("values", []) or []

        times: list[datetime] = []
        vals: list[Optional[float]] = []

        # Unit conversion logic for windSpeed only
        for item in values:
            t = self._parse_valid_time_start(item.get("validTime", ""))
            if t is None:
                continue
            v = item.get("value", None)
            if v is None:
                times.append(t)
                vals.append(None)
                continue

            # Convert units if needed
            if path == "windSpeed":
                # Common codes: "wmoUnit:km_h-1" or "wmoUnit:m_s-1"
                u = str(unit or "")
                if "m_s-1" in u:
                    v = _kt_from_mps(float(v))
                elif "km_h-1" in u or "km/h" in u:
                    v = _kt_from_kmh(float(v))
                else:
                    # Unknown; assume it's already m/s? We won't guess hard; treat as knots-ish
                    v = float(v)

            elif path == "probabilityOfPrecipitation":
                # percent -> 0..1
                v = float(v) / 100.0

            else:
                v = float(v)

            times.append(t)
            vals.append(v)

        return _GridSeries(times=times, values=vals)

    def _nearest_from_series(self, series: _GridSeries, t_local_naive: datetime) -> Optional[float]:
        if not series.times:
            return None
        # Compare in naive space to avoid TZ headaches for now
        idx = min(
            range(len(series.times)),
            key=lambda i: abs((series.times[i].replace(tzinfo=None) - t_local_naive).total_seconds()),
        )
        return series.values[idx]

    # ---------- Public API ----------

    def get_env_series(self, plan: TripPlan) -> list[EnvAtPoint]:
        start = _parse_local(plan.start_time_local)
        end = _parse_local(plan.end_time_local)
        step = timedelta(minutes=plan.sample_every_minutes)

        out: list[EnvAtPoint] = []
        t = start
        idx = 0
        npts = max(1, len(plan.route))

        while t <= end:
            p = plan.route[min(idx, npts - 1)]

            props = self._points_properties(p.lat, p.lon)
            hourly_url = props.get("forecastHourly")
            grid_url = props.get("forecastGridData")

            wind_speed_kt: Optional[float] = None
            wind_dir_deg: Optional[float] = None
            precip_prob: Optional[float] = None
            used: Optional[str] = None


            # Try hourly first
            used = "hourly"
            used = "forecastHourly"

            # Try hourly first
            if hourly_url:
                try:
                    periods = self._hourly_periods(hourly_url)
                    hp = self._pick_hourly(periods, t)
                    if hp:
                        wind_speed_kt = hp.wind_speed_kt
                        wind_dir_deg = hp.wind_dir_deg
                        precip_prob = hp.precip_prob
                        used = "forecastHourly"
                except requests.HTTPError as e:
                    used = f"forecastHourly_error_{getattr(e.response, 'status_code', 'err')}"

            # Fallback to grid data if needed
            if (wind_speed_kt is None and wind_dir_deg is None and precip_prob is None) and grid_url:
                grid = self._grid_json(grid_url)
                ws_series = self._series_from_grid(grid, "windSpeed")
                wd_series = self._series_from_grid(grid, "windDirection")
                pop_series = self._series_from_grid(grid, "probabilityOfPrecipitation")

                wind_speed_kt = self._nearest_from_series(ws_series, t)
                wind_dir_deg = self._nearest_from_series(wd_series, t)
                precip_prob = self._nearest_from_series(pop_series, t)

                if used is None or used.startswith("forecastHourly_error"):
                    used = "forecastGridData"

            meta = {"weather_source": "nws", "nws_path": used or "unknown"}

            out.append(
                EnvAtPoint(
                    t_local=t.strftime("%Y-%m-%d %H:%M"),
                    lat=p.lat,
                    lon=p.lon,
                    wind_speed_kt=float(wind_speed_kt or 0.0),
                    wind_gust_kt=None,
                    wind_dir_deg=wind_dir_deg,
                    wave_height_ft=None,
                    wave_period_s=None,
                    wave_dir_deg=None,
                    precip_prob=precip_prob,
                    tide_ft=None,
                    current_kt=None,
                    current_dir_deg=None,
                    meta=meta,
                )
            )


            t += step
            idx += 1

        return out
