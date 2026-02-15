"""Route normalization: resample irregular polylines into uniform-spacing points."""
from __future__ import annotations

import hashlib
import json
from math import atan2, cos, degrees, radians, sin, sqrt
from typing import List, Optional

from boat_ride.contracts.route_contract import NormalizedPoint, NormalizedRoute


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0  # Earth radius in metres
    lat1r, lon1r, lat2r, lon2r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = sin(dlat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing (degrees clockwise from true north)."""
    lat1r, lon1r, lat2r, lon2r = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2r - lon1r
    x = sin(dlon) * cos(lat2r)
    y = cos(lat1r) * sin(lat2r) - sin(lat1r) * cos(lat2r) * cos(dlon)
    return (degrees(atan2(x, y)) + 360.0) % 360.0


def _interpolate_point(
    lat1: float, lon1: float, lat2: float, lon2: float, frac: float
) -> tuple[float, float]:
    """Linear interpolation between two geographic points (frac in [0,1])."""
    lat = lat1 + frac * (lat2 - lat1)
    lon = lon1 + frac * (lon2 - lon1)
    return lat, lon


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_route(
    raw_points: List[dict],
    spacing_m: float = 500.0,
    route_id: str = "auto",
) -> NormalizedRoute:
    """
    Resample an irregular polyline into uniform-spacing points.

    Parameters
    ----------
    raw_points : list of dict
        Each dict must have ``lat`` and ``lon``; may have ``waterway``.
    spacing_m : float
        Target distance between resampled points (metres).
    route_id : str
        An identifier for the route.

    Returns
    -------
    NormalizedRoute
    """
    if not raw_points:
        return NormalizedRoute(
            route_version="1",
            route_id=route_id,
            spacing_m=spacing_m,
            total_distance_m=0.0,
            point_count=0,
            points=[],
        )

    # Build cumulative distance along raw segments
    cum: list[float] = [0.0]
    for i in range(1, len(raw_points)):
        d = _haversine_m(
            raw_points[i - 1]["lat"], raw_points[i - 1]["lon"],
            raw_points[i]["lat"], raw_points[i]["lon"],
        )
        cum.append(cum[-1] + d)

    total_dist = cum[-1]
    if total_dist == 0:
        p = raw_points[0]
        return NormalizedRoute(
            route_version="1",
            route_id=route_id,
            spacing_m=spacing_m,
            total_distance_m=0.0,
            point_count=1,
            points=[
                NormalizedPoint(
                    i=0,
                    lat=p["lat"],
                    lon=p["lon"],
                    cum_dist_m=0.0,
                    seg_dist_m=0.0,
                    bearing_deg_true=0.0,
                    waterway=p.get("waterway"),
                )
            ],
        )

    # Generate target distances along the route
    target_dists: list[float] = []
    d = 0.0
    while d <= total_dist:
        target_dists.append(d)
        d += spacing_m
    # Always include final point
    if not target_dists or target_dists[-1] < total_dist:
        target_dists.append(total_dist)

    # Walk raw segments and interpolate new points
    points: list[NormalizedPoint] = []
    seg_idx = 0  # current raw segment (seg_idx -> seg_idx+1)

    for idx, target_d in enumerate(target_dists):
        # Advance segment index until target_d falls within [cum[seg_idx], cum[seg_idx+1]]
        while seg_idx < len(raw_points) - 2 and cum[seg_idx + 1] < target_d:
            seg_idx += 1

        seg_len = cum[seg_idx + 1] - cum[seg_idx]
        if seg_len > 0:
            frac = (target_d - cum[seg_idx]) / seg_len
        else:
            frac = 0.0
        frac = max(0.0, min(1.0, frac))

        a = raw_points[seg_idx]
        b = raw_points[min(seg_idx + 1, len(raw_points) - 1)]
        lat, lon = _interpolate_point(a["lat"], a["lon"], b["lat"], b["lon"], frac)

        # Waterway: inherit from nearest raw point
        waterway = a.get("waterway") or b.get("waterway")

        seg_dist = target_d - (target_dists[idx - 1] if idx > 0 else 0.0)

        points.append(NormalizedPoint(
            i=idx,
            lat=lat,
            lon=lon,
            cum_dist_m=target_d,
            seg_dist_m=seg_dist,
            bearing_deg_true=0.0,  # filled below
            waterway=waterway,
        ))

    # Compute forward-looking bearing
    final_points: list[NormalizedPoint] = []
    for i, pt in enumerate(points):
        if i < len(points) - 1:
            nxt = points[i + 1]
            brg = _bearing_deg(pt.lat, pt.lon, nxt.lat, nxt.lon)
        elif len(points) >= 2:
            prv = points[i - 1]
            brg = _bearing_deg(prv.lat, prv.lon, pt.lat, pt.lon)
        else:
            brg = 0.0

        # Rebuild frozen dataclass with correct bearing
        final_points.append(NormalizedPoint(
            i=pt.i,
            lat=pt.lat,
            lon=pt.lon,
            cum_dist_m=pt.cum_dist_m,
            seg_dist_m=pt.seg_dist_m,
            bearing_deg_true=brg,
            waterway=pt.waterway,
        ))

    # Source hash for cache invalidation
    raw_hash = hashlib.md5(
        json.dumps([(p["lat"], p["lon"]) for p in raw_points]).encode()
    ).hexdigest()[:12]

    return NormalizedRoute(
        route_version="1",
        route_id=route_id,
        spacing_m=spacing_m,
        total_distance_m=total_dist,
        point_count=len(final_points),
        points=final_points,
        source_raw_hash=raw_hash,
    )
