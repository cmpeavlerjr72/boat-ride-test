# path: boat-ride/src/boat_ride/contracts/route_contract.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class NormalizedPoint:
    i: int
    lat: float
    lon: float
    cum_dist_m: float
    seg_dist_m: float
    bearing_deg_true: float  # maps to env.meta["route_heading_deg"]
    waterway: Optional[str] = None  # "inland" / "coastal" / "offshore"


@dataclass(frozen=True)
class NormalizedRoute:
    route_version: str
    route_id: str
    spacing_m: float
    total_distance_m: float
    point_count: int
    points: List[NormalizedPoint]
    source_raw_hash: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None