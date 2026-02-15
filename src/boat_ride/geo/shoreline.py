"""Download and cache Natural Earth 1:10m coastline as Shapely geometry."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Optional

import requests
import shapefile  # pyshp
from shapely.geometry import MultiLineString, shape


_NE_URL = (
    "https://naciscdn.org/naturalearth/10m/physical/"
    "ne_10m_coastline.zip"
)

_DEFAULT_DATA_DIR = Path.home() / ".boat_ride" / "data"


def _data_dir() -> Path:
    d = Path(os.environ.get("BOAT_RIDE_DATA_DIR", str(_DEFAULT_DATA_DIR)))
    d.mkdir(parents=True, exist_ok=True)
    return d


class ShorelineData:
    """Lazy-loading, in-memory cached coastline geometry."""

    _instance: Optional[ShorelineData] = None
    _coastline: Optional[MultiLineString] = None

    @classmethod
    def get(cls) -> ShorelineData:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def coastline(self) -> MultiLineString:
        if self._coastline is None:
            self._coastline = self._load()
        return self._coastline

    # ------------------------------------------------------------------

    def _load(self) -> MultiLineString:
        shp_path = self._ensure_downloaded()
        reader = shapefile.Reader(str(shp_path))
        lines = []
        for sr in reader.iterShapeRecords():
            geom = shape(sr.shape.__geo_interface__)
            if geom.geom_type == "LineString":
                lines.append(geom)
            elif geom.geom_type == "MultiLineString":
                lines.extend(geom.geoms)
        return MultiLineString(lines)

    def _ensure_downloaded(self) -> Path:
        d = _data_dir()
        shp_path = d / "ne_10m_coastline.shp"
        if shp_path.exists():
            return shp_path

        zip_path = d / "ne_10m_coastline.zip"
        if not zip_path.exists():
            print(f"[boat_ride] Downloading coastline shapefile …")
            r = requests.get(_NE_URL, timeout=120, stream=True)
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(d)

        if not shp_path.exists():
            raise FileNotFoundError(f"Expected {shp_path} after extracting zip")

        return shp_path
