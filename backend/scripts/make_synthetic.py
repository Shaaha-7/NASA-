"""Generate a SYNTHETIC test region so the whole app runs before any NASA data is downloaded.

Everything produced here is labelled TEST FIXTURE: it is invented terrain at an arbitrary
location, written in the same formats and projections as the real USGS products
(equirectangular GeoTIFF DEMs, a Transverse Mercator geologic shapefile, MMGIS-style GeoJSON),
so the real pipeline code path is exercised end to end.

Usage:  python backend/scripts/make_synthetic.py   (then: python backend/scripts/prepare_data.py synthetic)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.geo import MARS_RADIUS_M  # noqa: E402

LON0, LON1, LAT0, LAT1 = 120.00, 120.12, 10.00, 10.10
LONC, LATC = (LON0 + LON1) / 2, (LAT0 + LAT1) / 2
DEG_M = math.pi * MARS_RADIUS_M / 180
EQC = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"
OUT = config.DATA_DIR / "test_raw" / "synthetic"
rng = np.random.default_rng(42)

BOULDERS = np.column_stack([rng.uniform(-600, 600, 260), rng.uniform(-2200, -900, 260),
                            rng.uniform(1.5, 3.5, 260), rng.uniform(4, 7, 260)])


def true_xy(lon, lat):
    return (lon - LONC) * DEG_M * math.cos(math.radians(LATC)), (lat - LATC) * DEG_M


def terrain(x, y, detail=True):
    z = -2500.0 + 0.01 * x + 0.004 * y
    # crater
    r = np.hypot(x - 1900, y + 1300)
    R = 850.0
    z += np.where(r < R, -140 * (1 - (r / R) ** 2), 0) + 55 * np.exp(-((r - R) / 130) ** 2)
    # raised fan / plateau with a steep scarp and one gentle ramp near y = 1500
    w = 22 + 260 * np.exp(-((y - 1500) / 260) ** 2)
    edge = -1100 + 0.25 * (y - 0)
    z += 85 / (1 + np.exp((x - edge) / w)) * (1 / (1 + np.exp(-(y - 150) / 40)))
    # smooth hills
    z += 12 * np.sin(x / 700) * np.cos(y / 900)
    if detail:
        # dune field: short-wavelength ripples
        dune = (x > 100) & (x < 1700) & (y > 600) & (y < 2300)
        z += np.where(dune, 1.6 * np.sin(2 * np.pi * (x * 0.8 + y * 0.6) / 32), 0)
        # boulder field
        for bx, by, h, s in BOULDERS:
            d2 = (x - bx) ** 2 + (y - by) ** 2
            near = d2 < (4 * s) ** 2
            if near.any():
                z = z + np.where(near, h * np.exp(-d2 / (2 * s * s)), 0)
    return z


def write_dem(path, lon_a, lon_b, lat_a, lat_b, res_m, detail, offset=0.0, smooth=False):
    import rasterio
    from rasterio.transform import from_bounds
    x0, x1 = math.radians(lon_a) * MARS_RADIUS_M, math.radians(lon_b) * MARS_RADIUS_M
    y0, y1 = math.radians(lat_a) * MARS_RADIUS_M, math.radians(lat_b) * MARS_RADIUS_M
    w, h = int((x1 - x0) / res_m), int((y1 - y0) / res_m)
    xs = x0 + (np.arange(w) + 0.5) * (x1 - x0) / w
    ys = y1 - (np.arange(h) + 0.5) * (y1 - y0) / h
    lon = np.degrees(xs / MARS_RADIUS_M)
    lat = np.degrees(ys / MARS_RADIUS_M)
    LON, LAT = np.meshgrid(lon, lat)
    X, Y = true_xy(LON, LAT)
    Z = terrain(X, Y, detail).astype("float32") + offset
    if smooth:
        from scipy import ndimage
        Z = ndimage.gaussian_filter(Z, 1.0)
    nodata = -3.4028227e38
    with rasterio.open(path, "w", driver="GTiff", width=w, height=h, count=1, dtype="float32",
                       crs=EQC, transform=from_bounds(x0, y0, x1, y1, w, h), nodata=nodata,
                       compress="deflate") as dst:
        dst.write(Z, 1)
        dst.update_tags(NOTE="SYNTHETIC TEST FIXTURE - not real Mars terrain")
    return Z


def write_image(path, res_m, kind):
    import rasterio
    from rasterio.transform import from_bounds
    x0, x1 = math.radians(LON0 - 0.01) * MARS_RADIUS_M, math.radians(LON1 + 0.01) * MARS_RADIUS_M
    y0, y1 = math.radians(LAT0 - 0.01) * MARS_RADIUS_M, math.radians(LAT1 + 0.01) * MARS_RADIUS_M
    w, h = int((x1 - x0) / res_m), int((y1 - y0) / res_m)
    lon = np.degrees((x0 + (np.arange(w) + 0.5) * (x1 - x0) / w) / MARS_RADIUS_M)
    lat = np.degrees((y1 - (np.arange(h) + 0.5) * (y1 - y0) / h) / MARS_RADIUS_M)
    X, Y = true_xy(*np.meshgrid(lon, lat))
    Z = terrain(X, Y, detail=False)
    gy, gx = np.gradient(Z, res_m)
    shade = np.clip(0.6 - 0.9 * gx + 0.9 * gy, 0, 1)
    if kind == "ctx":
        img = (shade * 170 + 40 + rng.normal(0, 6, Z.shape)).clip(0, 255).astype("uint8")
        dtype, nod = "uint8", 0
    else:  # thermal-like: smooth brightness that differs by "unit"
        dune = (X > 100) & (X < 1700) & (Y > 600) & (Y < 2300)
        img = (200 + 8 * shade + np.where(dune, -6, 0)).astype("float32")
        dtype, nod = "float32", None
    with rasterio.open(path, "w", driver="GTiff", width=w, height=h, count=1, dtype=dtype, crs=EQC,
                       transform=from_bounds(x0, y0, x1, y1, w, h), nodata=nod, compress="deflate") as dst:
        dst.write(img, 1)


def write_units(path_stem: Path):
    import shapefile
    from pyproj import CRS, Transformer
    tm = CRS.from_proj4(f"+proj=tmerc +lat_0=0 +lon_0={LONC} +k=1 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs")
    geo = CRS.from_proj4("+proj=longlat +R=3396190 +no_defs")
    tf = Transformer.from_crs(geo, tm, always_xy=True)

    def ring(pts_xy):  # true local metres -> lon/lat -> TM
        out = []
        for x, y in pts_xy:
            lon = LONC + x / (DEG_M * math.cos(math.radians(LATC)))
            lat = LATC + y / DEG_M
            out.append(tf.transform(lon, lat))
        return out

    half_w, half_h = 3600, 3100
    units = [
        ("Synthetic floor unit", [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h), (-half_w, -half_h)]),
        ("Synthetic fan unit", [(-half_w, 150), (-1100 + 0.25 * 150, 150), (-1100 + 0.25 * half_h, half_h), (-half_w, half_h), (-half_w, 150)]),
        ("Synthetic aeolian bedform unit", [(100, 600), (1700, 600), (1700, 2300), (100, 2300), (100, 600)]),
        ("Synthetic crater rim unit", [(1900 + 1000 * math.cos(a), -1300 + 1000 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 40)]),
    ]
    w = shapefile.Writer(str(path_stem), shapeType=shapefile.POLYGON)
    w.field("UnitName", "C", 60)
    for name, pts in units:
        w.poly([ring(pts)[::-1]])  # shapefile exterior rings are clockwise
        w.record(name)
    w.close()
    path_stem.with_suffix(".prj").write_text(tm.to_wkt())


def write_waypoints(path):
    pts = [(-2600, -2400), (-2200, -1900), (-1700, -1500), (-1100, -1200), (-600, -600), (-100, -200),
           (400, 100), (900, 300), (1300, 200)]
    feats = []
    for i, (x, y) in enumerate(pts):
        lon = LONC + x / (DEG_M * math.cos(math.radians(LATC)))
        lat = LATC + y / DEG_M
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {"sol": 10 + i * 15, "site": i, "dist_km": round(i * 0.7, 2),
                                     "note": "SYNTHETIC TEST FIXTURE"}})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    line = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"note": "SYNTHETIC TEST FIXTURE"},
            "geometry": {"type": "LineString", "coordinates": [f["geometry"]["coordinates"] for f in feats]}}]}
    (path.parent / "SYNTH_traverse.json").write_text(json.dumps(line))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("[synthetic] writing test rasters to", OUT)
    # primary 'HiRISE-like' DEM: 4 m, covers the western ~75% of the box only (tests fallback fill)
    write_dem(OUT / "SYNTH_dem_primary_4m.tif", LON0 - 0.005, LON1 - 0.03, LAT0 - 0.005, LAT1 + 0.005, 4.0, True)
    # fallback 'CTX-like' DEM: 20 m, whole box, smoothed, with a +3 m datum offset (tests offset correction)
    write_dem(OUT / "SYNTH_dem_fallback_20m.tif", LON0 - 0.02, LON1 + 0.02, LAT0 - 0.02, LAT1 + 0.02, 20.0, False,
              offset=3.0, smooth=True)
    write_image(OUT / "SYNTH_ctx_ortho_6m.tif", 6.0, "ctx")
    write_image(OUT / "SYNTH_themis_day_100m.tif", 100.0, "themis")
    write_units(OUT / "SYNTH_GeoUnits")
    write_waypoints(OUT / "SYNTH_waypoints.json")
    print("[synthetic] done")


if __name__ == "__main__":
    main()
