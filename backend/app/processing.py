"""Raster processing shared by prepare_data.py and the synthetic test generator.

Rules enforced here (from the project outline):
* slope and roughness are computed ONLY from numerical elevation, never from images;
* NoData stays NaN all the way through and is never turned into 0;
* every derived product carries units, source and processing notes.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .geo import Grid, MARS_GEOGRAPHIC_PROJ

# ---------------------------------------------------------------- reading


def read_to_grid(path: Path, grid: Grid, resampling: str = "bilinear", band: int = 1) -> np.ndarray:
    """Reproject one band of any georeferenced raster onto `grid` (Mars lon/lat).

    Uses a WarpedVRT so only the needed part of a huge file is read.
    Returns float32 with NaN where the source has no data.
    """
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    rs = getattr(Resampling, resampling)
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"{path.name} has no CRS; cannot place it on Mars safely")
        nodata = src.nodata
        with WarpedVRT(src, crs=CRS.from_string(MARS_GEOGRAPHIC_PROJ), transform=grid.affine(),
                       width=grid.width, height=grid.height, resampling=rs,
                       src_nodata=nodata, nodata=np.nan, dtype="float32") as vrt:
            arr = vrt.read(band, masked=True).astype("float32")
    out = arr.filled(np.nan)
    # Many planetary DEMs use a large negative sentinel instead of a declared nodata.
    out[(out < -1e5) | (out > 1e5)] = np.nan
    return out


def raster_info(path: Path) -> dict:
    import rasterio
    with rasterio.open(path) as src:
        return {
            "file": path.name,
            "size_bytes": path.stat().st_size,
            "crs_wkt_head": (src.crs.to_wkt()[:160] + "...") if src.crs else None,
            "pixel_size": [abs(src.transform.a), abs(src.transform.e)],
            "width": src.width, "height": src.height, "count": src.count,
            "dtype": src.dtypes[0], "nodata": src.nodata,
            "units": (src.units[0] if src.units and src.units[0] else None),
        }

# ---------------------------------------------------------------- terrain


def slope_deg(elev: np.ndarray, grid: Grid) -> np.ndarray:
    """Slope magnitude (degrees) by central differences, in metres. NaN stays NaN."""
    dx = grid.dx_m_rows()[:, None]
    dzdy, dzdx = np.gradient(elev.astype("float64"))
    gx = dzdx / dx
    gy = dzdy / grid.dy_m
    s = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    s[~np.isfinite(elev)] = np.nan  # never report a slope where there is no elevation
    return s


def roughness_m(elev: np.ndarray, window: int = 5) -> np.ndarray:
    """Local roughness: standard deviation of elevation after removing the local mean
    surface (a detrended RMS height) in a window x window neighbourhood. Units: metres.
    Picks up boulder fields, ridges and scarps that average slope hides."""
    valid = np.isfinite(elev)
    # remove the local mean level first so float32 keeps centimetre precision
    base = float(np.nanmedian(elev)) if valid.any() else 0.0
    z = np.where(valid, elev - base, 0.0).astype("float32")
    w = valid.astype("float32")
    k = window
    cnt = ndimage.uniform_filter(w, k, mode="nearest")
    mean = ndimage.uniform_filter(z, k, mode="nearest") / np.maximum(cnt, 1e-9)
    resid = np.where(valid, z - mean, 0.0)
    var = ndimage.uniform_filter(resid ** 2, k, mode="nearest") / np.maximum(cnt, 1e-9)
    r = np.sqrt(np.maximum(var, 0)).astype("float32")
    r[~valid] = np.nan
    return r


def block_max_to_grid(fine: np.ndarray, fine_grid: Grid, grid: Grid) -> np.ndarray:
    """Aggregate a fine raster onto a coarser grid with the MAX of each coarse cell
    (conservative for hazards). Grids may not nest exactly."""
    rows = ((fine_grid.north - (np.arange(fine_grid.height) + 0.5) * fine_grid.dlat - grid.south)
            / grid.dlat)
    rows = grid.height - 1 - np.floor(rows).astype(int)
    cols = np.floor(((fine_grid.west + (np.arange(fine_grid.width) + 0.5) * fine_grid.dlon) - grid.west)
                    / grid.dlon).astype(int)
    rr = np.clip(rows, 0, grid.height - 1)
    cc = np.clip(cols, 0, grid.width - 1)
    out = np.full(grid.height * grid.width, -np.inf, dtype="float64")
    idx = (rr[:, None] * grid.width + cc[None, :]).ravel()
    vals = fine.ravel().astype("float64")
    ok = np.isfinite(vals)
    np.maximum.at(out, idx[ok], vals[ok])
    out[~np.isfinite(out)] = np.nan
    return out.reshape(grid.height, grid.width).astype("float32")


def hillshade(elev: np.ndarray, grid: Grid, azimuth=315.0, altitude=45.0) -> np.ndarray:
    dx = grid.dx_m_rows()[:, None]
    dzdy, dzdx = np.gradient(elev.astype("float64"))
    gx, gy = dzdx / dx, -dzdy / grid.dy_m  # gy positive = northward rise
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(azimuth), math.radians(altitude)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = np.clip(hs, 0, 1).astype("float32")
    hs[~np.isfinite(elev)] = np.nan
    return hs

# ---------------------------------------------------------------- images


def _interp_colors(values: np.ndarray, stops: list[tuple[float, str]]) -> np.ndarray:
    vs = np.array([s[0] for s in stops], dtype="float64")
    cols = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for _, c in stops], dtype="float64")
    v = np.clip(values, vs[0], vs[-1])
    out = np.zeros(values.shape + (3,), dtype="float64")
    for ch in range(3):
        out[..., ch] = np.interp(v, vs, cols[:, ch])
    return out


def save_png_colormap(arr: np.ndarray, path: Path, stops, alpha=220):
    rgb = _interp_colors(np.nan_to_num(arr, nan=stops[0][0]), stops)
    a = np.where(np.isfinite(arr), alpha, 0)
    img = np.dstack([rgb, a]).astype("uint8")
    Image.fromarray(img, "RGBA").save(path, optimize=True)


def save_png_gray(arr: np.ndarray, path: Path, lo=None, hi=None, alpha=255):
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        raise ValueError("no valid pixels")
    lo = np.percentile(finite, 1) if lo is None else lo
    hi = np.percentile(finite, 99) if hi is None else hi
    g = np.clip((arr - lo) / max(hi - lo, 1e-9), 0, 1) * 255
    a = np.where(np.isfinite(arr), alpha, 0)
    g = np.nan_to_num(g)
    img = np.dstack([g, g, g, a]).astype("uint8")
    Image.fromarray(img, "RGBA").save(path, optimize=True)
    return float(lo), float(hi)


def save_png_categorical(codes: np.ndarray, path: Path, palette: dict[int, str], alpha=170):
    h, w = codes.shape
    img = np.zeros((h, w, 4), dtype="uint8")
    for code, hexc in palette.items():
        m = codes == code
        img[m, 0] = int(hexc[1:3], 16)
        img[m, 1] = int(hexc[3:5], 16)
        img[m, 2] = int(hexc[5:7], 16)
        img[m, 3] = alpha
    Image.fromarray(img, "RGBA").save(path, optimize=True)


ELEV_STOPS = [(0.0, "#1d3b6e"), (0.25, "#2f7fa8"), (0.5, "#7fbf7b"), (0.75, "#e3c56b"), (1.0, "#b0523a")]
SLOPE_STOPS = [(0, "#2b8a3e"), (8, "#94d82d"), (15, "#fab005"), (25, "#e8590c"), (35, "#c92a2a"), (45, "#5c0f0f")]
ROUGH_STOPS = [(0, "#e7f5ff"), (0.25, "#74c0fc"), (0.75, "#f59f00"), (1.5, "#d6336c"), (3.0, "#5f0937")]
UNIT_PALETTE = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6",
                "#bcf60c", "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000", "#aaffc3",
                "#808000", "#ffd8b1", "#000075", "#808080"]

# ---------------------------------------------------------------- vectors


def rasterize_units(shp_path: Path, grid: Grid) -> tuple[np.ndarray, list[str], str]:
    """Rasterize a geologic-unit shapefile onto the grid. Returns (codes, unit_names, field).
    Reprojects with pyproj from the shapefile's own .prj (e.g. Mars Transverse Mercator)."""
    import shapefile  # pyshp
    from pyproj import CRS, Transformer
    from rasterio.features import rasterize

    prj = shp_path.with_suffix(".prj")
    if not prj.exists():
        raise ValueError(f"{shp_path.name}: missing .prj, cannot reproject safely")
    src_crs = CRS.from_wkt(prj.read_text(errors="ignore"))
    dst_crs = CRS.from_proj4(MARS_GEOGRAPHIC_PROJ.replace(" +type=crs", ""))
    tf = Transformer.from_crs(src_crs, dst_crs, always_xy=True)

    with shapefile.Reader(str(shp_path)) as sf:  # closed afterwards: Windows locks open files
        fields = [f[0] for f in sf.fields[1:]]
        recs = sf.records()
        shape_recs = list(sf.iterShapeRecords())
    # Pick the column holding readable unit names: the text column whose values most often contain
    # the word "unit" (e.g. "Jezero floor unit"); otherwise a conventional name; otherwise the first text column.
    text_fields = [f for f in fields if recs and any(isinstance(r[f], str) and r[f].strip() for r in recs)]
    scored = sorted(((sum("unit" in str(r[f]).lower() for r in recs), f) for f in text_fields), reverse=True)
    pref = ["UnitName", "Unit_Name", "UNITNAME", "Unit", "UNIT", "unit", "Name", "NAME", "Label", "LABEL", "UnitLabel"]
    if scored and scored[0][0] > 0:
        field = scored[0][1]
    else:
        field = next((p for p in pref if p in fields), None) or (text_fields[0] if text_fields else fields[0])

    def tx(coords):
        if isinstance(coords[0], (float, int)):
            x, y = tf.transform(coords[0], coords[1])
            return (x, y)
        return [tx(c) for c in coords]

    names: list[str] = []
    shapes = []
    for sr in shape_recs:
        name = str(sr.record[field]).strip() or "(unnamed)"
        if name not in names:
            names.append(name)
        gi = sr.shape.__geo_interface__
        if gi["type"] not in ("Polygon", "MultiPolygon"):
            continue
        geom = {"type": gi["type"], "coordinates": tx(gi["coordinates"])}
        shapes.append((geom, names.index(name)))
    codes = rasterize(shapes, out_shape=(grid.height, grid.width), transform=grid.affine(),
                      fill=-1, dtype="int16", all_touched=False) if shapes else \
        np.full((grid.height, grid.width), -1, dtype="int16")
    return codes, names, field


def unit_multipliers(names: list[str], penalties: dict) -> tuple[list[float], list[str | None], list[str | None]]:
    mults, flags, reasons = [], [], []
    for n in names:
        m, fl, rs = 1.0, None, None
        for rule in penalties.get("rules", []):
            if rule["keyword"].lower() in n.lower() and rule["multiplier"] > m:
                m, fl, rs = rule["multiplier"], rule.get("flag"), rule.get("reason")
        mults.append(m)
        flags.append(fl)
        reasons.append(rs)
    return mults, flags, reasons

# ---------------------------------------------------------------- hazards


def detect_hazards(slope: np.ndarray, rough: np.ndarray, grid: Grid, max_slope_deg: float,
                   rough_max_m: float, min_area_m2: float = 2000.0, limit: int = 60) -> list[dict]:
    """Rule-based hazard zones: connected areas steeper than the EVA slope limit, or
    rougher than the roughness limit. Each zone becomes a GeoJSON feature with its rule,
    metric and data basis. These are MODEL-DERIVED, not observed obstacles."""
    feats = []
    cell_area = grid.dy_m * float(grid.dx_m_rows().mean())
    for kind, arr, thr, unit, rule in (
        ("steep_slope", slope, max_slope_deg, "deg", f"slope > {max_slope_deg} deg (EVA slope limit)"),
        ("rough_terrain", rough, rough_max_m, "m", f"roughness > {rough_max_m} m (EVA roughness limit)"),
    ):
        mask = np.isfinite(arr) & (arr > thr)
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        if n == 0:
            continue
        idx = np.arange(1, n + 1)
        areas = ndimage.sum(mask, lab, idx) * cell_area
        maxes = ndimage.maximum(np.nan_to_num(arr), lab, idx)
        objs = ndimage.find_objects(lab)
        order = np.argsort(-areas)
        for k in order[:limit]:
            if areas[k] < min_area_m2:
                break
            sl = objs[k]
            rr, cc = np.nonzero(lab[sl] == k + 1)
            r0, c0 = sl[0].start, sl[1].start
            rc, ccn = int(rr.mean()) + r0, int(cc.mean()) + c0
            lon, lat = grid.center_of(rc, ccn)
            w_, s_ = grid.center_of(sl[0].stop - 1, sl[1].start)
            e_, n_ = grid.center_of(sl[0].start, sl[1].stop - 1)
            severity = "high" if (maxes[k] > thr * 1.4) else "moderate"
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {
                    "id": f"hz-{kind}-{len(feats)+1:03d}",
                    "type": kind,
                    "severity": severity,
                    "rule": rule,
                    "metric": {"max": round(float(maxes[k]), 2), "unit": unit, "threshold": thr},
                    "area_m2": round(float(areas[k]), 0),
                    "bbox": [round(w_, 6), round(s_, 6), round(e_, 6), round(n_, 6)],
                    "measured_or_derived": "model-derived from numerical elevation",
                },
            })
    return feats


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
