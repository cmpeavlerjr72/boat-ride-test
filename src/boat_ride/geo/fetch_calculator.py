"""Ray-cast fetch computation against coastline geometry."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import Dict, List, Optional

from shapely.geometry import LineString, MultiLineString, Point, box
from shapely.ops import nearest_points
from shapely import prepare

from boat_ride.geo.shoreline import ShorelineData


_NM_TO_DEG = 1.0 / 60.0  # 1 nm ≈ 1 arcminute
_M_TO_NM = 1.0 / 1852.0

# Ray parameters
_NUM_RAYS = 16  # every 22.5 deg
_RAY_STEP_DEG = 360.0 / _NUM_RAYS
_MAX_RAY_NM = 50.0
_MAX_RAY_DEG = _MAX_RAY_NM * _NM_TO_DEG
_BBOX_BUFFER_DEG = _MAX_RAY_DEG + 0.1


@dataclass
class FetchResult:
    """Fetch distances (nm) by compass direction for a single point."""
    direction_fetch_nm: Dict[float, float] = field(default_factory=dict)
    min_fetch_nm: float = 0.0
    max_fetch_nm: float = 0.0
    waterway: str = "offshore"  # auto-classified


def _classify_waterway(min_fetch_nm: float) -> str:
    if min_fetch_nm < 3.0:
        return "inland"
    if min_fetch_nm < 20.0:
        return "coastal"
    return "offshore"


def effective_fetch_nm(result: FetchResult, wind_dir_deg: float) -> float:
    """
    SPM-style weighted average of fetch in directions within 45 deg of wind.

    Uses cos^2 weighting for directions within ±45° of the wind direction.
    """
    if not result.direction_fetch_nm:
        return result.min_fetch_nm

    total_weight = 0.0
    weighted_sum = 0.0

    for direction, fetch_nm in result.direction_fetch_nm.items():
        # Angular difference between this ray direction and the wind direction
        diff = abs(direction - wind_dir_deg) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff
        if diff <= 45.0:
            w = cos(radians(diff)) ** 2
            weighted_sum += w * fetch_nm
            total_weight += w

    if total_weight <= 0:
        return result.min_fetch_nm

    return weighted_sum / total_weight


class FetchCalculator:
    """Computes open-water fetch by ray-casting against coastline data."""

    def __init__(self, shoreline: Optional[ShorelineData] = None):
        self._shore = shoreline or ShorelineData.get()
        self._clipped_cache: Dict[str, MultiLineString] = {}

    def _clip_coastline(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> MultiLineString:
        key = f"{min_lon:.2f},{min_lat:.2f},{max_lon:.2f},{max_lat:.2f}"
        if key in self._clipped_cache:
            return self._clipped_cache[key]

        bbox = box(min_lon, min_lat, max_lon, max_lat)
        clipped = self._shore.coastline.intersection(bbox)

        if clipped.is_empty:
            result = MultiLineString()
        elif clipped.geom_type == "LineString":
            result = MultiLineString([clipped])
        elif clipped.geom_type == "MultiLineString":
            result = clipped
        else:
            # GeometryCollection - extract lines
            lines = []
            for geom in clipped.geoms:
                if geom.geom_type == "LineString":
                    lines.append(geom)
                elif geom.geom_type == "MultiLineString":
                    lines.extend(geom.geoms)
            result = MultiLineString(lines)

        self._clipped_cache[key] = result
        return result

    def compute_fetch(self, lat: float, lon: float) -> FetchResult:
        """Compute fetch for a single point by ray-casting in 16 directions."""
        # Clip coastline to local region for performance
        coast = self._clip_coastline(
            lon - _BBOX_BUFFER_DEG,
            lat - _BBOX_BUFFER_DEG,
            lon + _BBOX_BUFFER_DEG,
            lat + _BBOX_BUFFER_DEG,
        )

        direction_fetch: Dict[float, float] = {}
        origin = Point(lon, lat)

        for i in range(_NUM_RAYS):
            direction_deg = i * _RAY_STEP_DEG  # 0, 22.5, 45, ...
            rad = radians(direction_deg)
            # End point of ray (note: lon = x, lat = y)
            end_lon = lon + _MAX_RAY_DEG * sin(rad)
            end_lat = lat + _MAX_RAY_DEG * cos(rad)
            ray = LineString([(lon, lat), (end_lon, end_lat)])

            if coast.is_empty:
                # No coastline nearby -> max fetch
                direction_fetch[direction_deg] = _MAX_RAY_NM
                continue

            intersection = ray.intersection(coast)
            if intersection.is_empty:
                direction_fetch[direction_deg] = _MAX_RAY_NM
            else:
                # Find nearest intersection point
                if intersection.geom_type == "Point":
                    hit = intersection
                elif intersection.geom_type == "MultiPoint":
                    hit = min(intersection.geoms, key=lambda p: origin.distance(p))
                else:
                    # LineString or collection - get nearest point
                    hit, _ = nearest_points(origin, intersection)

                # Distance in degrees -> approximate nm
                dist_deg = origin.distance(hit)
                dist_nm = dist_deg / _NM_TO_DEG
                direction_fetch[direction_deg] = max(0.01, min(dist_nm, _MAX_RAY_NM))

        fetches = list(direction_fetch.values())
        min_f = min(fetches) if fetches else 0.0
        max_f = max(fetches) if fetches else 0.0

        return FetchResult(
            direction_fetch_nm=direction_fetch,
            min_fetch_nm=min_f,
            max_fetch_nm=max_f,
            waterway=_classify_waterway(min_f),
        )

    def compute_fetch_batch(
        self, points: List[tuple[float, float]]
    ) -> List[FetchResult]:
        """Compute fetch for multiple (lat, lon) points."""
        if not points:
            return []

        # Compute a single bounding box for all points + buffer
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        # Pre-clip coastline to the overall bounding box
        self._clip_coastline(
            min(lons) - _BBOX_BUFFER_DEG,
            min(lats) - _BBOX_BUFFER_DEG,
            max(lons) + _BBOX_BUFFER_DEG,
            max(lats) + _BBOX_BUFFER_DEG,
        )

        return [self.compute_fetch(lat, lon) for lat, lon in points]
