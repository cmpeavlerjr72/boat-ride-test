"""Centralized settings for the boat-ride backend."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "BOAT_RIDE_"}

    # Redis — empty string means disabled (graceful fallback)
    redis_url: str = ""

    # Supabase — empty strings mean disabled (graceful fallback)
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""

    # TTL values in seconds for each cached data type
    ttl_nws_points: int = 86400       # 24 h — NWS /points metadata rarely changes
    ttl_nws_hourly: int = 3600        # 1 h — hourly forecast
    ttl_nws_grid: int = 3600          # 1 h — grid data forecast
    ttl_ndbc_stations: int = 86400    # 24 h — active station list
    ttl_ndbc_realtime: int = 1800     # 30 min — realtime buoy observations
    ttl_ndbc_has_waves: int = 604800  # 7 d — whether station has wave columns
    ttl_coops_stations: int = 86400   # 24 h — CO-OPS station list
    ttl_coops_tides: int = 21600      # 6 h — tide predictions
    ttl_fetch_result: int = 2592000   # 30 d — coastline fetch ray-cast

    # Background worker
    worker_interval_s: int = 300      # 5 min between warming cycles

    # Gunicorn
    gunicorn_workers: int = 2


settings = Settings()
