"""Offline package: everything one region needs with the network off.

Package = processed region folder (terrain, overlays, pins, hazards, manifest)
        + Mars Trek context tiles cached for that region
        + cached DONKI space-weather window
        + assistant document index
The web app shell itself is cached by the browser's service worker (frontend/sw.js).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import zipfile
from pathlib import Path

from . import assistant, config, netutil, spaceweather
from .region_store import get_region

TILES = config.CACHE_DIR / "tiles"


def tile_path(layer: str, z: int, y: int, x: int) -> Path:
    ext = config.TREK_LAYERS[layer][1]
    return TILES / layer / str(z) / str(y) / f"{x}.{ext}"


def fetch_tile(layer: str, z: int, y: int, x: int) -> Path | None:
    p = tile_path(layer, z, y, x)
    if p.exists():
        return p
    if not netutil.is_online():
        return None
    name, ext = config.TREK_LAYERS[layer][:2]
    url = config.TREK_TILE_TEMPLATE.format(layer=name, z=z, y=y, x=x, ext=ext)
    try:
        r = netutil.get(url, timeout=15)
    except Exception:
        return None
    if not r.content or not r.headers.get("content-type", "").startswith("image"):
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(r.content)
    return p


def tiles_for_bbox(bbox: dict, zmin: int, zmax: int):
    """Tile indices for Leaflet's EPSG4326 scheme used by Trek EQ (2 x 1 tiles at zoom 0)."""
    for z in range(zmin, zmax + 1):
        span = 180.0 / (2 ** z)
        x0 = int(math.floor((bbox["west"] + 180) / span))
        x1 = int(math.floor((bbox["east"] + 180) / span))
        y0 = int(math.floor((90 - bbox["north"]) / span))
        y1 = int(math.floor((90 - bbox["south"]) / span))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                yield z, y, x


def prefetch(region_id: str, zmax: int = 9, layers: list[str] | None = None) -> dict:
    region = get_region(region_id)
    if region is None:
        raise ValueError(f"region {region_id} not prepared")
    layers = layers or list(config.TREK_LAYERS)
    report = {"region_id": region_id, "tiles_ok": 0, "tiles_missing": 0, "donki": None, "assistant": None}
    b = region.manifest["bbox"]
    pad = 0.3
    big = {"west": max(-180, b["west"] - pad), "east": min(180, b["east"] + pad),
           "south": max(-90, b["south"] - pad), "north": min(90, b["north"] + pad)}
    jobs = [(l, z, y, x) for l in layers for (z, y, x) in tiles_for_bbox({"west": -180, "east": 179.99, "south": -89.99, "north": 90}, 0, 2)]
    jobs += [(l, z, y, x) for l in layers for (z, y, x) in tiles_for_bbox(big, 3, zmax)]
    for l, z, y, x in jobs:
        if fetch_tile(l, z, y, x):
            report["tiles_ok"] += 1
        else:
            report["tiles_missing"] += 1
    try:
        spaceweather.refresh(30)
        report["donki"] = "refreshed"
    except Exception as e:
        report["donki"] = f"not refreshed: {spaceweather._clean(e)[:120]}"
    try:
        report["assistant"] = assistant.build_index()
    except Exception as e:
        report["assistant"] = f"index not built: {e}"
    return report


def _files(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file()] if folder.exists() else []


def manifest(region_id: str) -> dict:
    region = get_region(region_id)
    if region is None:
        raise ValueError(f"region {region_id} not prepared")
    rfiles = _files(region.folder)
    tfiles = _files(TILES)
    donki = config.CACHE_DIR / "donki.json"
    idx = assistant.INDEX
    m = region.manifest
    return {
        "region_id": region_id, "name": m["name"], "is_test_fixture": region.is_test_fixture,
        "data_date": m.get("data_date"), "processed_at": m.get("processed_at"),
        "ready_offline": {"terrain_and_layers": True, "context_tiles": len(tfiles) > 0,
                          "space_weather_cache": donki.exists(), "assistant_index": idx.exists()},
        "files": [{"path": str(p.relative_to(region.folder)), "bytes": p.stat().st_size} for p in rfiles],
        "region_bytes": sum(p.stat().st_size for p in rfiles),
        "tiles": {"count": len(tfiles), "bytes": sum(p.stat().st_size for p in tfiles)},
        "space_weather_fetched_at": json.loads(donki.read_text()).get("fetched_at") if donki.exists() else None,
        "assistant_index_built": dt.datetime.fromtimestamp(idx.stat().st_mtime).isoformat(timespec="seconds") if idx.exists() else None,
        "online_now": netutil.is_online(),
        "note": "Anything not in this package (other regions, live data) is unavailable offline and the app says so.",
    }


def build_zip(region_id: str) -> Path:
    region = get_region(region_id)
    if region is None:
        raise ValueError(f"region {region_id} not prepared")
    out = config.CACHE_DIR / f"marspath_offline_{region_id}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in _files(region.folder):
            z.write(p, Path("data/processed") / region_id / p.relative_to(region.folder))
        for p in _files(TILES):
            z.write(p, Path("data/cache/tiles") / p.relative_to(TILES))
        for extra in (config.CACHE_DIR / "donki.json", assistant.INDEX):
            if extra.exists():
                z.write(extra, Path("data/cache") / extra.name)
        z.writestr("PACKAGE_INFO.json", json.dumps(manifest(region_id), indent=2))
    return out
