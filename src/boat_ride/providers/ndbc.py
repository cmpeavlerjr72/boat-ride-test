from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import math
import xml.etree.ElementTree as ET

import requests

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.base import EnvProvider

import time
from requests.exceptions import ReadTimeout, ConnectionError




def _parse_local(dt_str: str, tz_name: Optional[str] = None) -> datetime:
    from boat_ride.core.models import _parse_local as _pl
    return _pl(dt_str, tz_name)


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # nautical miles
    r_km = 6371.0
    to_rad = math.radians
    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    km = r_km * c
    return km * 0.539957  # km -> nm


@dataclass(frozen=True)
class Station:
    station_id: str
    lat: float
    lon: float
    name: str = ""


class NDBCWaveProvider(EnvProvider):
    """
    NDBC real-time buoy waves via:
      - Active station list: https://www.ndbc.noaa.gov/activestations.xml
      - Realtime standard met files: https://www.ndbc.noaa.gov/data/realtime2/{STATION}.txt

    We parse WVHT (m), DPD (s), MWD (deg true) when present.
    """

    ACTIVE_XML = "https://www.ndbc.noaa.gov/activestations.xml"
    REALTIME_TXT = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

    def __init__(self, user_agent: str = "BoatRidePOC/0.0.1 (contact: you@example.com)"):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent})
        self._stations: Optional[list[Station]] = None
        self._station_file_cache: dict[str, str] = {}  # station -> raw txt
        self._station_has_waves: dict[str, bool] = {}  # station -> has WVHT/DPD/MWD columns

    def dump_station_preview(self, station_id: str, n: int = 5) -> None:
        txt = self._get_station_txt(station_id)
        if not txt:
            print(f"No realtime2 file found for {station_id}")
            return
        lines = [ln.rstrip("\n") for ln in txt.splitlines() if ln.strip()]
        print("\n".join(lines[:n]))


    def _get_text(self, url: str, timeout: int = 25, tries: int = 4, backoff_s: float = 0.8) -> Optional[str]:
        last_err: Exception | None = None
        for attempt in range(tries):
            try:
                r = self.s.get(url, timeout=timeout)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.text
            except (ReadTimeout, ConnectionError) as e:
                last_err = e
                time.sleep(backoff_s * (2 ** attempt))
        raise last_err if last_err else RuntimeError("Unknown request failure")


    def _load_stations(self) -> list[Station]:
        if self._stations is not None:
            return self._stations

        r = self.s.get(self.ACTIVE_XML, timeout=25)
        r.raise_for_status()
        xml_text = r.text

        root = ET.fromstring(xml_text)
        stations: list[Station] = []
        # <station id="41012" lat="30.06" lon="-87.55" name="..."/>
        for node in root.findall(".//station"):
            sid = node.attrib.get("id")
            lat = node.attrib.get("lat")
            lon = node.attrib.get("lon")
            if not sid or lat is None or lon is None:
                continue
            try:
                stations.append(
                    Station(
                        station_id=str(sid).strip(),
                        lat=float(lat),
                        lon=float(lon),
                        name=str(node.attrib.get("name", "")).strip(),
                    )
                )
            except Exception:
                continue

        self._stations = stations
        return stations

    def _get_station_txt(self, station: str) -> Optional[str]:
        if station in self._station_file_cache:
            return self._station_file_cache[station]

        url = self.REALTIME_TXT.format(station=station)
        txt = self._get_text(url, timeout=25, tries=4, backoff_s=0.8)
        if txt is None:
            return None
        self._station_file_cache[station] = txt
        return txt


    def _pick_nearest_station(self, lat: float, lon: float, max_nm: float = 200.0) -> Optional[tuple[str, float]]:

        stations = self._load_stations()
        # Sort by distance; try closest first
        ranked = sorted(stations, key=lambda s: _haversine_nm(lat, lon, s.lat, s.lon))

        for s in ranked[:50]:  # avoid scanning thousands
            d = _haversine_nm(lat, lon, s.lat, s.lon)
            if d > max_nm:
                break

            # If we already know whether it has waves, use that
            if s.station_id in self._station_has_waves and not self._station_has_waves[s.station_id]:
                continue

            txt = self._get_station_txt(s.station_id)
            if not txt:
                self._station_has_waves[s.station_id] = False
                continue

            lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            if len(lines) < 3:
                self._station_has_waves[s.station_id] = False
                continue

            header = lines[0].lstrip("#").split()
            if "WVHT" in header:
                self._station_has_waves[s.station_id] = True
                return (s.station_id, d)


            self._station_has_waves[s.station_id] = False

        return None

    def _parse_station_waves_nearest_time(
        self, station_txt: str, t_local: datetime
    ) -> tuple[Optional[float], Optional[float], Optional[float], Optional[datetime]]:
        """
        Returns (wave_height_ft, dominant_period_s, mean_wave_dir_deg, obs_dt).

        NDBC timestamps are UTC. We construct UTC-aware datetimes and compare
        against the (potentially aware) sample time.
        """
        lines = [ln.strip() for ln in station_txt.splitlines() if ln.strip()]
        if len(lines) < 3:
            return (None, None, None, None)

        header = lines[0].lstrip("#").split()
        # second header line is units, then data
        data_lines = lines[2:]

        def idx(col: str) -> Optional[int]:
            return header.index(col) if col in header else None

        i_wvht = idx("WVHT")
        i_dpd = idx("DPD")
        i_apd = idx("APD")
        i_mwd = idx("MWD")
        i_yy = idx("YY")
        i_mm = idx("MM")
        i_dd = idx("DD")
        i_hh = idx("hh")
        i_min = idx("mm")

        if None in (i_wvht, i_mwd, i_yy, i_mm, i_dd, i_hh):
            return (None, None, None, None)
        if i_dpd is None and i_apd is None:
            return (None, None, None, None)


        best_dt: Optional[datetime] = None
        best_vals: tuple[Optional[float], Optional[float], Optional[float]] = (None, None, None)
        best_abs = float("inf")

        # Scan a limited number of recent rows (most recent at top)
        for ln in data_lines[:200]:
            parts = ln.split()
            try:
                yy = int(parts[i_yy])
                mm = int(parts[i_mm])
                dd = int(parts[i_dd])
                hh = int(parts[i_hh])
                minute = int(parts[i_min]) if i_min is not None and i_min < len(parts) else 0

                # NDBC YY is 2-digit
                yy_raw = int(parts[i_yy])

                # If file provides 4-digit year, use it directly
                if yy_raw >= 1900:
                    year = yy_raw
                else:
                    # 2-digit year mapping
                    year = 2000 + yy_raw if yy_raw < 70 else 1900 + yy_raw

                dt = datetime(year, mm, dd, hh, minute, tzinfo=timezone.utc)

                # values can be "MM"
                def parse_float(p: str) -> Optional[float]:
                    if p in ("MM", "99", "999"):
                        return None
                    try:
                        return float(p)
                    except Exception:
                        return None

                wvht_m = parse_float(parts[i_wvht]) if i_wvht is not None else None
                dpd_s = parse_float(parts[i_dpd]) if i_dpd is not None else None
                apd_s = parse_float(parts[i_apd]) if i_apd is not None else None

                period_s = dpd_s if dpd_s is not None else apd_s
                mwd_deg = parse_float(parts[i_mwd]) if i_mwd is not None else None

                # Compare aware datetimes; strip tz if mismatched
                cmp_dt = dt
                cmp_tl = t_local
                if cmp_dt.tzinfo is not None and cmp_tl.tzinfo is None:
                    cmp_dt = cmp_dt.replace(tzinfo=None)
                elif cmp_dt.tzinfo is None and cmp_tl.tzinfo is not None:
                    cmp_tl = cmp_tl.replace(tzinfo=None)
                abs_sec = abs((cmp_dt - cmp_tl).total_seconds())
                if abs_sec < best_abs:
                    best_abs = abs_sec
                    best_dt = dt
                    # convert meters -> feet
                    wvht_ft = (wvht_m * 3.28084) if wvht_m is not None else None
                    best_vals = (wvht_ft, period_s, mwd_deg)
            except Exception:
                continue

        return (*best_vals, best_dt)


    def get_env_series(self, plan: TripPlan) -> list[EnvAtPoint]:
        times = plan.sample_times
        out: list[EnvAtPoint] = []
        npts = max(1, len(plan.route))

        for idx, t in enumerate(times):
            p = plan.route[min(idx, npts - 1)]

            station_pick = self._pick_nearest_station(p.lat, p.lon)
            wave_height_ft = wave_period_s = wave_dir_deg = None
            meta = {"waves_source": "ndbc", "ndbc_station": None, "ndbc_distance_nm": None, "ndbc_obs_time": None}


            if station_pick:
                station_id, dist_nm = station_pick
                meta["ndbc_station"] = station_id
                meta["ndbc_distance_nm"] = round(dist_nm, 1)

                txt = self._get_station_txt(station_id)
                if txt:
                    wave_height_ft, wave_period_s, wave_dir_deg, obs_dt = self._parse_station_waves_nearest_time(txt, t)
                    if obs_dt:
                        meta["ndbc_obs_time"] = obs_dt.strftime("%Y-%m-%d %H:%M")

            # Return EnvAtPoint with only wave fields filled (others left None/0)
            out.append(
                EnvAtPoint(
                    t_local=t.strftime("%Y-%m-%d %H:%M"),
                    lat=p.lat,
                    lon=p.lon,

                    # IMPORTANT: wave provider should not overwrite weather fields
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
