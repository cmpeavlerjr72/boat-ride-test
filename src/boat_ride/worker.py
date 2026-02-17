"""Background cache warmer for boat-ride.

Reads recently-requested areas from a Redis sorted set, generates
representative grid points, and pre-fetches weather data so user
requests hit warm caches.

Run with:  python -m boat_ride.worker
"""
from __future__ import annotations

import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def _grid_points(min_lat: float, min_lon: float, max_lat: float, max_lon: float, cap: int = 50):
    """Generate a uniform grid of (lat, lon) within the bounding box, capped."""
    import math

    dlat = max_lat - min_lat
    dlon = max_lon - min_lon
    # Aim for roughly square spacing
    area = dlat * dlon
    if area <= 0:
        return [(min_lat, min_lon)]

    n = min(cap, max(1, int(math.sqrt(cap * area / max(0.01, dlat * dlon)))))
    step_lat = dlat / max(n, 1)
    step_lon = dlon / max(n, 1)

    pts = []
    lat = min_lat
    while lat <= max_lat and len(pts) < cap:
        lon = min_lon
        while lon <= max_lon and len(pts) < cap:
            pts.append((round(lat, 4), round(lon, 4)))
            lon += step_lon if step_lon > 0 else 1
        lat += step_lat if step_lat > 0 else 1
    return pts


def _warm_nws(lat: float, lon: float) -> None:
    """Pre-fetch NWS /points + forecastHourly for a single coordinate."""
    try:
        from boat_ride.providers.nws import NWSProvider

        prov = NWSProvider()
        props = prov._points_properties(lat, lon)
        hourly_url = props.get("forecastHourly")
        if hourly_url:
            try:
                prov._hourly_periods(hourly_url)
            except Exception:
                pass
        grid_url = props.get("forecastGridData")
        if grid_url:
            try:
                prov._grid_json(grid_url)
            except Exception:
                pass
    except Exception as exc:
        log.debug("NWS warm failed for (%.4f, %.4f): %s", lat, lon, exc)


def _warm_ndbc_stations() -> None:
    """Pre-fetch the NDBC active station list."""
    try:
        from boat_ride.providers.ndbc import NDBCWaveProvider

        prov = NDBCWaveProvider()
        stations = prov._load_stations()
        log.info("NDBC stations cached: %d", len(stations))
    except Exception as exc:
        log.warning("NDBC station warm failed: %s", exc)


def _warm_coops_stations() -> None:
    """Pre-fetch the CO-OPS station list."""
    try:
        from boat_ride.providers.coops import COOPSTideProvider

        prov = COOPSTideProvider()
        stations = prov._load_stations()
        log.info("CO-OPS stations cached: %d", len(stations))
    except Exception as exc:
        log.warning("CO-OPS station warm failed: %s", exc)


def _get_active_areas(max_age_s: int = 86400):
    """Return list of (min_lat, min_lon, max_lat, max_lon) from the active areas sorted set."""
    from boat_ride.cache.redis_client import get_redis
    from boat_ride.cache.keys import worker_active_areas

    r = get_redis()
    if r is None:
        return []

    cutoff = time.time() - max_age_s
    # Remove entries older than max_age_s
    r.zremrangebyscore(worker_active_areas(), "-inf", cutoff)
    # Get remaining entries
    members = r.zrange(worker_active_areas(), 0, -1)
    areas = []
    for m in members:
        try:
            parts = m.split(",")
            areas.append(tuple(float(x) for x in parts))
        except Exception:
            continue
    return areas


def run_cycle() -> None:
    """Run one warming cycle."""
    areas = _get_active_areas()
    if not areas:
        log.info("No active areas to warm")
        return

    log.info("Warming %d active area(s)", len(areas))

    # Station lists (cheap, do every cycle)
    _warm_ndbc_stations()
    _warm_coops_stations()

    # NWS grid points within each area
    for area in areas:
        min_lat, min_lon, max_lat, max_lon = area
        pts = _grid_points(min_lat, min_lon, max_lat, max_lon, cap=50)
        log.info("Area (%.2f,%.2f)-(%.2f,%.2f): warming %d NWS points",
                 min_lat, min_lon, max_lat, max_lon, len(pts))
        for lat, lon in pts:
            _warm_nws(lat, lon)
            # Small sleep to avoid hammering NWS
            time.sleep(0.2)


def main() -> None:
    from boat_ride.config import settings

    log.info("Worker starting (interval=%ds)", settings.worker_interval_s)

    from boat_ride.cache.redis_client import get_redis

    r = get_redis()
    if r is None:
        log.error("Redis not available — worker cannot run without it. "
                   "Set BOAT_RIDE_REDIS_URL and try again.")
        return

    while True:
        try:
            run_cycle()
        except Exception as exc:
            log.exception("Worker cycle error: %s", exc)
        log.info("Sleeping %ds until next cycle", settings.worker_interval_s)
        time.sleep(settings.worker_interval_s)


if __name__ == "__main__":
    main()
