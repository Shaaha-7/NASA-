"""Measured weather at the science sites, from Perseverance's MEDA instrument.

The per-sol summaries are built by backend/scripts/fetch_meda.py and stored in
config/weather/<region>_meda.json. They are historical measurements at the rover on the sol it
worked at each site: never live conditions and never a forecast.
"""
from __future__ import annotations

import json
from functools import lru_cache

from . import config
from .geo import haversine_m


@lru_cache(maxsize=8)
def _load(region_id: str, mtime: float) -> dict | None:
    f = config.CONFIG_DIR / "weather" / f"{region_id}_meda.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _data(region_id: str) -> dict | None:
    f = config.CONFIG_DIR / "weather" / f"{region_id}_meda.json"
    return _load(region_id, f.stat().st_mtime) if f.exists() else None


def for_site(region, site_id: str | None = None, lon: float | None = None, lat: float | None = None) -> dict:
    d = _data(region.region_id)
    base = {"available": False, "region_id": region.region_id, "kind": "historical measurement, not live"}
    if not d:
        return {**base, "reason": "MEDA weather is not loaded for this region (run backend/scripts/fetch_meda.py)."}
    sites = {f["properties"]["id"]: f for f in region.read_geojson("science_sites.geojson").get("features", [])}
    dist = None
    if site_id is None and lon is not None and lat is not None:
        cands = [(haversine_m(lon, lat, *f["geometry"]["coordinates"][:2]), sid) for sid, f in sites.items()
                 if sid in d["sites"]]
        if cands:
            dist, site_id = min(cands)
    rec = d["sites"].get(site_id or "")
    if not rec:
        return {**base, "reason": "No MEDA record for this site."}
    has = any(rec.get(k) for k in ("air_temp_c", "ground_temp_c", "pressure_pa", "wind_speed_ms"))
    return {**base, "available": bool(has), "site_id": site_id, "site_name": rec.get("site_name"), "sol": rec.get("sol"),
            "distance_m": None if dist is None else round(dist, 1),
            "air_temp_c": rec.get("air_temp_c"), "ground_temp_c": rec.get("ground_temp_c"),
            "pressure_pa": rec.get("pressure_pa"), "wind_speed_ms": rec.get("wind_speed_ms"),
            "files": rec.get("files", {}), "source": d.get("source"), "source_url": d.get("source_url"),
            "method": d.get("method"), "notes": d.get("notes", [])}


def all_sites(region) -> dict:
    d = _data(region.region_id)
    if not d:
        return {"available": False, "sites": {}}
    return {"available": True, "source": d.get("source"), "source_url": d.get("source_url"), "method": d.get("method"),
            "notes": d.get("notes", []), "sites": d.get("sites", {})}
