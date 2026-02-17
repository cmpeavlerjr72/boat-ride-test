"""Redis key naming conventions for the boat-ride cache layer."""
from __future__ import annotations

import hashlib

_PREFIX = "br"


# ── NWS ──────────────────────────────────────────────────────────────────

def nws_points(lat: float, lon: float) -> str:
    """Key for NWS /points/{lat},{lon} properties."""
    return f"{_PREFIX}:nws:points:{lat:.4f},{lon:.4f}"


def nws_hourly(url: str) -> str:
    """Key for NWS forecastHourly response (URL-based)."""
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{_PREFIX}:nws:hourly:{h}"


def nws_grid(url: str) -> str:
    """Key for NWS forecastGridData response (URL-based)."""
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{_PREFIX}:nws:grid:{h}"


# ── NDBC ─────────────────────────────────────────────────────────────────

def ndbc_stations() -> str:
    return f"{_PREFIX}:ndbc:stations"


def ndbc_realtime(station_id: str) -> str:
    return f"{_PREFIX}:ndbc:realtime:{station_id}"


def ndbc_has_waves(station_id: str) -> str:
    return f"{_PREFIX}:ndbc:has_waves:{station_id}"


# ── CO-OPS ───────────────────────────────────────────────────────────────

def coops_stations() -> str:
    return f"{_PREFIX}:coops:stations"


def coops_tides(station_id: str, begin: str, end: str) -> str:
    """begin/end are already formatted strings like '202601220200'."""
    h = hashlib.sha256(f"{station_id}:{begin}:{end}".encode()).hexdigest()[:16]
    return f"{_PREFIX}:coops:tides:{h}"


# ── Fetch ────────────────────────────────────────────────────────────────

def fetch_result(lat: float, lon: float) -> str:
    return f"{_PREFIX}:fetch:{lat:.6f},{lon:.6f}"


# ── Worker ───────────────────────────────────────────────────────────────

def worker_active_areas() -> str:
    return f"{_PREFIX}:worker:active_areas"
