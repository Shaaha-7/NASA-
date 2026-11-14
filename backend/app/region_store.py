"""Loads processed regions from data/processed/<region_id>/ and keeps them in memory."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np

from . import config
from .geo import Grid


class Region:
    def __init__(self, folder: Path):
        self.folder = folder
        with open(folder / "manifest.json", encoding="utf-8") as f:
            self.manifest = json.load(f)
        self.region_id = self.manifest["region_id"]
        self.is_test_fixture = bool(self.manifest.get("is_test_fixture"))
        self.grid = Grid.from_dict(self.manifest["grid"])
        with np.load(folder / "terrain.npz") as z:
            self.elev = z["elevation"].astype("float64")
            self.slope = z["slope_deg"].astype("float64")
            self.rough = z["roughness_m"].astype("float64")
            self.units = z["geo_unit"].astype("int16")
            self.dem_source = z["dem_source"].astype("uint8")
        self.elev_flat = np.ascontiguousarray(self.elev.ravel())
        self.slope_flat = np.ascontiguousarray(self.slope.ravel())
        self.rough_flat = np.ascontiguousarray(self.rough.ravel())
        self.units_flat = np.ascontiguousarray(self.units.ravel())
        self.dem_source_flat = np.ascontiguousarray(self.dem_source.ravel())
        self.dx_rows = np.ascontiguousarray(self.grid.dx_m_rows().astype("float64"))
        unit_mult = np.array([u["multiplier"] for u in self.manifest.get("units", [])] + [1.0], dtype="float64")
        # index -1 (no unit) maps to the trailing 1.0
        self.unit_mult_flat = np.ascontiguousarray(unit_mult[np.where(self.units_flat < 0, len(unit_mult) - 1, self.units_flat)])

    def sample(self, lon: float, lat: float) -> dict:
        r, c = self.grid.cell_of(lon, lat)
        u = int(self.units[r, c])
        units = self.manifest.get("units", [])

        def val(a):
            v = float(a[r, c])
            return None if not np.isfinite(v) else round(v, 2)
        src = {0: None, 1: "primary", 2: "fallback"}[int(self.dem_source[r, c])]
        return {"lon": lon, "lat": lat, "cell": [r, c], "inside": self.grid.contains(lon, lat),
                "elevation_m": val(self.elev), "slope_deg": val(self.slope), "roughness_m": val(self.rough),
                "geologic_unit": units[u]["name"] if 0 <= u < len(units) else None, "dem_source": src}

    def read_geojson(self, name: str) -> dict:
        p = self.folder / name
        if not p.exists():
            return {"type": "FeatureCollection", "features": []}
        with open(p, encoding="utf-8") as f:
            return json.load(f)


_cache: dict[str, Region] = {}
_lock = threading.Lock()


def available_region_ids() -> list[str]:
    if not config.PROCESSED_DIR.exists():
        return []
    return sorted(p.name for p in config.PROCESSED_DIR.iterdir()
                  if p.is_dir() and not p.name.startswith(".") and (p / "manifest.json").exists())


def get_region(region_id: str) -> Region | None:
    with _lock:
        folder = config.PROCESSED_DIR / region_id
        if not (folder / "manifest.json").exists():
            _cache.pop(region_id, None)
            return None
        mtime = (folder / "manifest.json").stat().st_mtime
        r = _cache.get(region_id)
        if r is None or getattr(r, "_mtime", None) != mtime:
            r = Region(folder)
            r._mtime = mtime
            _cache[region_id] = r
        return r
