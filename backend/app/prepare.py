"""Region preparation pipeline: raw NASA/USGS files -> one processed, offline-ready region.

Run through scripts/prepare_data.py. Raw files are never modified; everything is written
to data/processed/<region_id>/ together with a manifest describing sources and processing.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np

from . import config
from .geo import Grid, COORDINATE_CONVENTION, norm_lon
from .processing import (
    ELEV_STOPS, ROUGH_STOPS, SLOPE_STOPS, UNIT_PALETTE, block_max_to_grid, detect_hazards, hillshade,
    raster_info, rasterize_units, read_to_grid, roughness_m, save_png_categorical, save_png_colormap,
    save_png_gray, slope_deg, unit_multipliers, write_json,
)

PROCESSING_VERSION = "1.0.0"
MAX_FINE_CELLS = 16_000_000  # keeps peak memory under ~1 GB on a laptop


def log(msg: str) -> None:
    print(f"[prepare] {msg}", flush=True)


def find_input(raw_dir: Path, patterns: list[str]) -> Path | None:
    files = [p for p in raw_dir.rglob("*") if p.is_file()]
    for pat in patterns:
        hits = sorted(p for p in files if fnmatch.fnmatch(p.name.lower(), pat.lower()))
        if hits:
            return max(hits, key=lambda p: p.stat().st_size)
    return None


def find_vector_units(raw_dir: Path, patterns: list[str]) -> tuple[Path | None, str | None]:
    """Find the geologic-unit POLYGONS: a shapefile by pattern, or a polygon layer inside an
    Esri File Geodatabase (*.gdb folder) or GeoPackage. Annotation/label, contact and line
    layers are skipped."""
    p = find_input(raw_dir, patterns)
    if p is not None:
        return p, None
    containers = [d for d in raw_dir.rglob("*.gdb") if d.is_dir()] + list(raw_dir.rglob("*.gpkg"))
    if not containers:
        return None, None
    try:
        import pyogrio
    except ImportError:
        log("  geodatabase found but 'pyogrio' is not installed: pip install pyogrio")
        return None, None
    skip = ("anno", "label", "contact", "line", "symbol", "point", "struct", "fault", "crater_rim", "boundary")
    keys = ["geounits", "geo_units", "geologicunits", "geounit", "unitpolys", "units", "polygons"]
    seen, best = [], None
    for c in containers:
        try:
            layers = pyogrio.list_layers(str(c))
        except Exception as e:
            log(f"  cannot read {c.name}: {e}")
            continue
        for name, gtype in layers:
            n, g = str(name).lower(), str(gtype).lower()
            seen.append(f"{c.name}/{name} ({gtype})")
            if not ("polygon" in g or "surface" in g):
                continue
            if any(k in n for k in skip):
                continue
            score = max((len(k) + (10 if n.endswith(k) else 0) for k in keys if k in n), default=1)
            if best is None or score > best[0]:
                best = (score, c, str(name))
    log("  vector layers found: " + "; ".join(seen))
    if best:
        log(f"  geologic units: using polygon layer '{best[2]}' in {best[1].name}")
        return best[1], best[2]
    log("  no geologic-unit polygon layer recognised (see list above)")
    return None, None


def vector_to_shapefile(container: Path, layer: str, out_dir: Path) -> Path:
    """Copy one layer of a geodatabase/GeoPackage to a temporary shapefile (curves linearised)."""
    import warnings
    from pyogrio.raw import read, write
    meta, _, geom, fields = read(str(container), layer=layer, force_2d=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{layer}.shp"
    gtype = "MultiPolygon" if "polygon" in str(meta.get("geometry_type", "")).lower() or "surface" in str(meta.get("geometry_type", "")).lower() else meta.get("geometry_type")
    # keep only text/number attribute columns (blob columns cannot go into a shapefile)
    keep = [i for i, f in enumerate(fields) if getattr(f, "dtype", None) is not None and f.dtype.kind in "OUifb"
            and not (len(f) and isinstance(f[0], (bytes, bytearray)))]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write(str(out), geom, [fields[i] for i in keep], [meta["fields"][i] for i in keep], crs=meta["crs"],
              geometry_type=gtype, driver="ESRI Shapefile", encoding="UTF-8")
    return out


def _swap_into_place(tmp: Path, out: Path) -> None:
    """Replace the processed region folder. Windows refuses to rename folders that something
    (antivirus, Explorer, a running server) is touching, so retry and fall back to copying."""
    import time
    old = out.with_name(f".{out.name}.old")
    for attempt in range(6):
        try:
            if old.exists():
                shutil.rmtree(old, ignore_errors=True)
            if out.exists():
                out.rename(old)
            tmp.rename(out)
            shutil.rmtree(old, ignore_errors=True)
            return
        except PermissionError:
            time.sleep(1.0 + attempt)
    log("  folder rename blocked by Windows; copying files instead")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(tmp, out, dirs_exist_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)


def _sha_head(path: Path, n=4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(n))
    return h.hexdigest()[:16]


def _source_entry(key: str, spec: dict, path: Path | None) -> dict:
    e = {"key": key, "label": spec.get("label"), "mission": spec.get("mission"),
         "instrument": spec.get("instrument"), "source_url": spec.get("url"),
         "nominal_resolution_m": spec.get("nominal_resolution_m"), "found": path is not None}
    if path is not None and path.is_dir():
        e.update(file=path.name, size_bytes=sum(f.stat().st_size for f in path.rglob("*") if f.is_file()),
                 file_modified=dt.datetime.fromtimestamp(path.stat().st_mtime).date().isoformat())
    elif path is not None:
        e.update(file=path.name, size_bytes=path.stat().st_size, sha256_head=_sha_head(path),
                 file_modified=dt.datetime.fromtimestamp(path.stat().st_mtime).date().isoformat())
    return e


def _overlay_grid(bbox: dict, max_px: int, min_res_m: float) -> Grid:
    g = Grid.from_bbox(bbox["west"], bbox["south"], bbox["east"], bbox["north"], min_res_m)
    scale = max(g.width, g.height) / max_px
    if scale > 1:
        g = Grid.from_bbox(bbox["west"], bbox["south"], bbox["east"], bbox["north"], min_res_m * scale)
    return g


def prepare_region(region_id: str, raw_dir: Path | None = None, out_root: Path | None = None) -> Path:
    cfg = config.region_config(region_id)
    if cfg is None:
        raise SystemExit(f"No config/regions/{region_id}.json")
    raw_dir = raw_dir or (config.DATA_DIR / cfg["raw_dir"] if cfg.get("raw_dir") else config.RAW_DIR)
    if not raw_dir.exists():
        raise SystemExit(f"Raw data folder not found: {raw_dir}")
    log(f"reading raw files from {raw_dir}")
    out_root = out_root or config.PROCESSED_DIR
    out = out_root / region_id
    tmp = out_root / f".{region_id}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "layers").mkdir(parents=True)

    bbox = cfg["bbox"]
    bbox = {k: (norm_lon(v) if k in ("west", "east") else v) for k, v in bbox.items()}
    grid = Grid.from_bbox(bbox["west"], bbox["south"], bbox["east"], bbox["north"], cfg["routing_resolution_m"])
    log(f"region {region_id}: grid {grid.width} x {grid.height} cells at ~{grid.mean_res_m:.1f} m")

    inputs = {k: find_input(raw_dir, spec["patterns"]) for k, spec in cfg["inputs"].items() if k != "geo_units"}
    units_layer = None
    if "geo_units" in cfg["inputs"]:
        inputs["geo_units"], units_layer = find_vector_units(raw_dir, cfg["inputs"]["geo_units"]["patterns"])
    sources = {k: _source_entry(k, cfg["inputs"][k], p) for k, p in inputs.items()}
    for k, p in inputs.items():
        log(f"  input {k:16s} -> {p.name if p else 'NOT FOUND'}")
    if not inputs.get("dem_primary") and not inputs.get("dem_fallback"):
        raise SystemExit("No elevation model found in data/raw. Download the CTX DEM or HiRISE DTM first.")

    notes: list[str] = []
    layers: list[dict] = []

    # ---------------- elevation (numerical DEMs only)
    elev_p = read_to_grid(inputs["dem_primary"], grid) if inputs.get("dem_primary") else None
    elev_f = read_to_grid(inputs["dem_fallback"], grid) if inputs.get("dem_fallback") else None
    for k in ("dem_primary", "dem_fallback"):
        if inputs.get(k):
            sources[k]["raster"] = raster_info(inputs[k])
    elev = np.full((grid.height, grid.width), np.nan, dtype="float32")
    dem_source = np.zeros_like(elev, dtype="uint8")  # 0 none, 1 primary, 2 fallback
    offset = 0.0
    if elev_p is not None:
        m = np.isfinite(elev_p)
        elev[m] = elev_p[m]
        dem_source[m] = 1
    if elev_f is not None:
        if elev_p is not None:
            both = np.isfinite(elev_p) & np.isfinite(elev_f)
            if both.sum() > 100:
                offset = float(np.median(elev_p[both] - elev_f[both]))
                notes.append(f"Fallback DEM shifted by median offset {offset:+.2f} m to match the primary DEM "
                             f"(computed over {int(both.sum())} overlapping cells).")
        fill = ~np.isfinite(elev) & np.isfinite(elev_f)
        elev[fill] = elev_f[fill] + offset
        dem_source[fill] = 2
    cover = float(np.isfinite(elev).mean())
    log(f"  elevation coverage {cover*100:.1f}% (primary {float((dem_source==1).mean())*100:.1f}%, "
        f"fallback {float((dem_source==2).mean())*100:.1f}%)")
    if cover < 0.05:
        raise SystemExit("Elevation covers <5% of the study box: check the bbox and that the DEM is for this region.")

    slope = slope_deg(elev, grid)

    # ---------------- roughness from the finest DEM available
    fine_res = float(cfg.get("fine_resolution_m", grid.mean_res_m))
    rough = None
    if inputs.get("dem_primary"):
        fg = Grid.from_bbox(bbox["west"], bbox["south"], bbox["east"], bbox["north"], fine_res)
        if fg.width * fg.height > MAX_FINE_CELLS:
            f = math.sqrt(fg.width * fg.height / MAX_FINE_CELLS)
            fine_res *= f
            fg = Grid.from_bbox(bbox["west"], bbox["south"], bbox["east"], bbox["north"], fine_res)
            notes.append(f"Roughness computed at {fine_res:.1f} m (coarsened to fit memory).")
        log(f"  roughness from primary DEM at ~{fg.mean_res_m:.1f} m ({fg.width} x {fg.height})")
        fine = read_to_grid(inputs["dem_primary"], fg)
        rough_f = roughness_m(fine, window=5)
        rough = block_max_to_grid(rough_f, fg, grid)
        del fine, rough_f
    rough_coarse = roughness_m(elev, window=3)
    if rough is None:
        rough = rough_coarse
        notes.append("Roughness from the routing-resolution DEM only (no high-resolution DEM found): "
                     "small obstacles are not resolved.")
    else:
        gap = ~np.isfinite(rough) & np.isfinite(rough_coarse)
        rough[gap] = rough_coarse[gap]
    rough[~np.isfinite(elev)] = np.nan

    # ---------------- geologic units
    units = np.full(elev.shape, -1, dtype="int16")
    unit_names: list[str] = []
    unit_field = None
    if inputs.get("geo_units"):
        shp = inputs["geo_units"]
        vec_tmp = config.CACHE_DIR / "_vector_tmp"
        shutil.rmtree(vec_tmp, ignore_errors=True)
        if units_layer:  # layer inside a geodatabase / GeoPackage
            shp = vector_to_shapefile(shp, units_layer, vec_tmp)
            sources["geo_units"]["layer"] = units_layer
        units, unit_names, unit_field = rasterize_units(shp, grid)
        shutil.rmtree(vec_tmp, ignore_errors=True)
        if len(unit_names) > 150:
            notes.append(f"Geologic layer gave {len(unit_names)} distinct names: it may not be the unit polygons.")
        log(f"  geologic units: {len(unit_names)} names from field '{unit_field}'")
    mults, flags, reasons = unit_multipliers(unit_names, config.geo_penalties())
    units_table = [{"code": i, "name": n, "multiplier": mults[i], "flag": flags[i], "reason": reasons[i],
                    "color": UNIT_PALETTE[i % len(UNIT_PALETTE)]} for i, n in enumerate(unit_names)]

    np.savez_compressed(tmp / "terrain.npz", elevation=elev, slope_deg=slope, roughness_m=rough,
                        geo_unit=units, dem_source=dem_source)

    # ---------------- overlays
    lb = grid.leaflet_bounds()
    common = {"bounds": lb, "kind": "image"}
    fin = elev[np.isfinite(elev)]
    emin, emax = float(np.percentile(fin, 1)), float(np.percentile(fin, 99))
    norm = (elev - emin) / max(emax - emin, 1e-6)
    save_png_colormap(norm, tmp / "layers" / "elevation.png", ELEV_STOPS, alpha=210)
    dem_src_key = "dem_primary" if inputs.get("dem_primary") else "dem_fallback"
    dem_meta = {"mission": sources[dem_src_key]["mission"], "instrument": sources[dem_src_key]["instrument"],
                "source": sources[dem_src_key]["label"], "source_url": sources[dem_src_key]["source_url"]}
    layers.append({**common, "id": "elevation", "name": "Elevation", "url": "layers/elevation.png",
                   "units": "m", "legend": {"type": "gradient", "min": round(emin, 1), "max": round(emax, 1),
                                            "stops": [[round(emin + s * (emax - emin), 1), c] for s, c in ELEV_STOPS]},
                   **dem_meta, "resolution_m": round(grid.mean_res_m, 1),
                   "processing": "Reprojected to Mars lon/lat grid (bilinear); primary DEM with fallback fill.",
                   "measured_or_derived": "measured (stereo photogrammetry DEM)",
                   "limitations": "Elevation relative to the source DEM's vertical datum.", "default_on": False,
                   "opacity": 0.6})
    hs = hillshade(elev, grid)
    save_png_gray(hs, tmp / "layers" / "hillshade.png", 0, 1, alpha=255)
    layers.append({**common, "id": "hillshade", "name": "Hillshade (from DEM)", "url": "layers/hillshade.png",
                   "units": "relative illumination", "legend": None, **dem_meta, "resolution_m": round(grid.mean_res_m, 1),
                   "processing": "Hillshade, sun azimuth 315 deg, altitude 45 deg. Visual only: never used for slope.",
                   "measured_or_derived": "derived (visualisation)", "limitations": "Visual aid only.",
                   "default_on": True, "opacity": 1.0})
    save_png_colormap(slope, tmp / "layers" / "slope.png", SLOPE_STOPS, alpha=200)
    layers.append({**common, "id": "slope", "name": "Slope", "url": "layers/slope.png", "units": "deg",
                   "legend": {"type": "gradient", "stops": [[v, c] for v, c in SLOPE_STOPS]}, **dem_meta,
                   "resolution_m": round(grid.mean_res_m, 1),
                   "processing": "Central differences on the numerical DEM in metres (Mars sphere).",
                   "measured_or_derived": "derived from numerical elevation",
                   "limitations": "Slope at grid resolution; steeper short slopes may exist.", "default_on": False,
                   "opacity": 0.65})
    save_png_colormap(rough, tmp / "layers" / "roughness.png", ROUGH_STOPS, alpha=200)
    layers.append({**common, "id": "roughness", "name": "Roughness", "url": "layers/roughness.png", "units": "m",
                   "legend": {"type": "gradient", "stops": [[v, c] for v, c in ROUGH_STOPS]}, **dem_meta,
                   "resolution_m": round(grid.mean_res_m, 1),
                   "processing": f"Detrended RMS height in a 5x5 window on the ~{fine_res:.0f} m DEM, max per routing cell.",
                   "measured_or_derived": "derived from numerical elevation",
                   "limitations": "Rocks smaller than the DEM resolution are not resolved.", "default_on": False,
                   "opacity": 0.65})
    if unit_names:
        save_png_categorical(units, tmp / "layers" / "geology.png",
                             {u["code"]: u["color"] for u in units_table}, alpha=150)
        s = sources["geo_units"]
        layers.append({**common, "id": "geology", "name": "Geologic units", "url": "layers/geology.png", "units": None,
                       "legend": {"type": "categorical", "items": [[u["name"], u["color"]] for u in units_table]},
                       "mission": s["mission"], "instrument": s["instrument"], "source": s["label"],
                       "source_url": s["source_url"], "resolution_m": round(grid.mean_res_m, 1),
                       "processing": f"Polygons reprojected from the map's own projection and rasterized (field '{unit_field}').",
                       "measured_or_derived": "interpreted (geologic mapping at 1:75,000)",
                       "limitations": "Map scale 1:75,000: unit boundaries are approximate at walking scale.",
                       "default_on": False, "opacity": 0.55})

    def image_layer(key, lid, name, units_label, measured, limitation, max_px, default_on, opacity, stretch=True):
        p = inputs.get(key)
        if not p:
            return
        spec = cfg["inputs"][key]
        og = _overlay_grid(bbox, max_px, float(spec.get("nominal_resolution_m") or grid.mean_res_m))
        try:
            arr = read_to_grid(p, og, resampling="average")
        except Exception as e:  # keep going: one bad optional layer must not stop the pipeline
            notes.append(f"Layer {lid} skipped: {e}")
            log(f"  WARNING {lid}: {e}")
            return
        if not np.isfinite(arr).any():
            notes.append(f"Layer {lid}: no coverage inside the study box.")
            return
        lo, hi = save_png_gray(arr, tmp / "layers" / f"{lid}.png")
        sources[key]["raster"] = raster_info(p)
        layers.append({"bounds": og.leaflet_bounds(), "kind": "image", "id": lid, "name": name,
                       "url": f"layers/{lid}.png", "units": units_label,
                       "legend": {"type": "stretch", "min": round(lo, 3), "max": round(hi, 3)},
                       "mission": spec["mission"], "instrument": spec["instrument"], "source": spec["label"],
                       "source_url": spec["url"], "resolution_m": round(og.mean_res_m, 2),
                       "coverage_fraction": round(float(np.isfinite(arr).mean()), 3),
                       "processing": "Reprojected to Mars lon/lat (area average), 1-99% contrast stretch.",
                       "measured_or_derived": measured, "limitations": limitation,
                       "default_on": default_on, "opacity": opacity})
        log(f"  layer {lid}: {og.width} x {og.height} px")

    image_layer("ortho_ctx", "ctx", "CTX imagery", "DN (image brightness)", "measured (visible image)",
                "Image brightness is not elevation and not a hazard measure.", cfg.get("overlay_max_px", 2048), True, 1.0)
    image_layer("ortho_hirise", "hirise", "HiRISE imagery", "DN (image brightness)", "measured (visible image)",
                "Imagery alone is not automated obstacle detection.", cfg.get("overlay_max_px", 2048), False, 1.0)
    image_layer("themis_day", "themis_day", "THEMIS day IR", "relative brightness temperature (stretched)",
                "measured (thermal infrared)", "Thermal context, not a direct hazard measure; acquisition dates vary.",
                1024, False, 0.7)
    image_layer("themis_night", "themis_night", "THEMIS night IR", "relative brightness temperature (stretched)",
                "measured (thermal infrared)", "Night IR relates to thermal inertia (loose vs consolidated surface); "
                "not a direct hazard measure.", 1024, False, 0.7)

    # show the DEM hillshade by default only when there is no imagery to look at
    if any(l["id"] in ("ctx", "hirise") for l in layers):
        for l in layers:
            if l["id"] == "hillshade":
                l["default_on"] = False
    # base map order: imagery first
    order = {"ctx": 0, "hirise": 1, "hillshade": 2, "themis_day": 3, "themis_night": 4, "elevation": 5,
             "slope": 6, "roughness": 7, "geology": 8}
    layers.sort(key=lambda l: order.get(l["id"], 99))

    # ---------------- rover data -> verified science points
    def clip_geojson(key):
        p = inputs.get(key)
        if not p:
            return None
        with open(p, encoding="utf-8") as f:
            gj = json.load(f)
        m = 0.01
        keep = []
        for ft in gj.get("features", []):
            g = ft.get("geometry") or {}
            if g.get("type") == "Point":
                lon, lat = g["coordinates"][:2]
                if bbox["west"] - m <= norm_lon(lon) <= bbox["east"] + m and bbox["south"] - m <= lat <= bbox["north"] + m:
                    keep.append(ft)
            elif g.get("type") in ("LineString", "MultiLineString"):
                lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
                if any(bbox["west"] - m <= norm_lon(x) <= bbox["east"] + m and bbox["south"] - m <= y <= bbox["north"] + m
                       for line in lines for x, y, *_ in line):
                    keep.append(ft)
        return {"type": "FeatureCollection", "features": keep}

    wp = clip_geojson("rover_waypoints")
    sites = []
    if wp:
        for ft in wp["features"]:
            p = ft.get("properties", {})
            sol = p.get("sol", p.get("SOL"))
            lon, lat = ft["geometry"]["coordinates"][:2]
            sites.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [norm_lon(lon), lat]},
                          "properties": {"id": f"wp-{sol if sol is not None else len(sites)}", "kind": "rover_waypoint",
                                         "name": f"Perseverance stop, sol {sol}" if sol is not None else "Perseverance stop",
                                         "sol": sol, "mission": "Mars 2020", "instrument": "Rover localization",
                                         "source": sources["rover_waypoints"]["label"],
                                         "source_url": sources["rover_waypoints"]["source_url"],
                                         "raw_images_url": "https://mars.nasa.gov/mars2020/multimedia/raw-images/",
                                         "original_properties": p,
                                         "measured_or_derived": "measured (rover position)"}})
        log(f"  rover waypoints in box: {len(sites)}")
    write_json(tmp / "rover_waypoints.geojson", {"type": "FeatureCollection", "features": sites})
    tr = clip_geojson("rover_traverse")
    write_json(tmp / "rover_traverse.geojson", tr or {"type": "FeatureCollection", "features": []})
    # curated science sites (filled by the team, each with a real source)
    curated_src = config.CONFIG_DIR / "science_sites" / f"{region_id}.geojson"
    if curated_src.exists():
        shutil.copy(curated_src, tmp / "science_sites.geojson")
    else:
        write_json(tmp / "science_sites.geojson", {"type": "FeatureCollection", "features": []})

    # ---------------- hazards (rule-based, model-derived)
    eva = config.eva_defaults()
    hz = detect_hazards(slope, rough, grid, eva["max_slope_deg"]["value"], eva["roughness_max_m"]["value"])
    for f in hz:
        f["properties"].update({"source": dem_meta["source"], "source_url": dem_meta["source_url"],
                                "data_resolution_m": round(grid.mean_res_m, 1)})
    write_json(tmp / "hazards.geojson", {"type": "FeatureCollection", "features": hz})
    log(f"  hazard zones: {len(hz)}")

    # ---------------- manifest
    data_dates = [s.get("file_modified") for s in sources.values() if s.get("file_modified")]
    manifest = {
        "region_id": region_id, "name": cfg["name"], "is_test_fixture": bool(cfg.get("is_test_fixture")),
        "bbox": bbox, "center": [(bbox["west"] + bbox["east"]) / 2, (bbox["south"] + bbox["north"]) / 2],
        "grid": grid.to_dict(), "coordinate_convention": COORDINATE_CONVENTION,
        "processing_version": PROCESSING_VERSION,
        "processed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data_date": max(data_dates) if data_dates else None,
        "elevation_stats": {"min_m": float(np.nanmin(elev)), "max_m": float(np.nanmax(elev)),
                            "coverage_fraction": round(cover, 4),
                            "primary_fraction": round(float((dem_source == 1).mean()), 4),
                            "fallback_fraction": round(float((dem_source == 2).mean()), 4),
                            "fallback_offset_m": round(offset, 3)},
        "fine_resolution_m": round(fine_res, 2),
        "units": units_table, "unit_field": unit_field,
        "sources": sources, "layers": layers, "science_goals": cfg.get("science_goals", []),
        "notes": notes,
    }
    write_json(tmp / "manifest.json", manifest)

    _swap_into_place(tmp, out)
    log(f"done -> {out}")
    return out
