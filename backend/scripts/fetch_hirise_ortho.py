"""Download only the study-box part of the USGS 25 cm HiRISE orthomosaic for a region.

Source (USGS Astrogeology, for Mars 2020 surface operations, published 2020-07-24, use constraints "None"):
  JEZ_hirise_soc_007_orthoMosaic_25cm_Ortho_blend120.tif  (3.41 GB, 81064 x 85936 px, uint8, 256x256 LZW tiles,
  orthographic projection on the Mars 2000 sphere centred 18.4663 N, 77.4298 E)
The file is internally tiled, so GDAL reads just the tiles inside the study box over HTTP.
The crop keeps the native 25 cm pixels and projection (no resampling), so rock shadows are preserved.

Usage:  python backend/scripts/fetch_hirise_ortho.py jezero [--margin-m 100]
Writes: <MARSPATH_DATA>/raw/<region>/JEZ_hirise_soc_007_orthoMosaic_25cm_crop_<region>.tif
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import config  # noqa: E402

SOURCE_URL = ("https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/"
              "JEZ_hirise_soc_007_orthoMosaic_25cm_Ortho_blend120.tif")
STRIP_ROWS = 2048


def source_window(src, bbox: dict, margin_m: float) -> Window:
    """Pixel window of the source that covers the lon/lat study box (edges densified, plus a margin)."""
    geo = CRS(src.crs).geodetic_crs
    tr = Transformer.from_crs(geo, src.crs, always_xy=True)
    xs, ys = [], []
    for t in np.linspace(0, 1, 41):
        for lon, lat in ((bbox["west"] + t * (bbox["east"] - bbox["west"]), bbox["south"]),
                         (bbox["west"] + t * (bbox["east"] - bbox["west"]), bbox["north"]),
                         (bbox["west"], bbox["south"] + t * (bbox["north"] - bbox["south"])),
                         (bbox["east"], bbox["south"] + t * (bbox["north"] - bbox["south"]))):
            x, y = tr.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    left, right = min(xs) - margin_m, max(xs) + margin_m
    bottom, top = min(ys) - margin_m, max(ys) + margin_m
    inv = ~src.transform
    c0, r0 = inv * (left, top)
    c1, r1 = inv * (right, bottom)
    c0, r0 = max(0, math.floor(c0)), max(0, math.floor(r0))
    c1, r1 = min(src.width, math.ceil(c1)), min(src.height, math.ceil(r1))
    if c1 <= c0 or r1 <= r0:
        raise SystemExit("The study box does not overlap the HiRISE orthomosaic")
    return Window(c0, r0, c1 - c0, r1 - r0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("region")
    ap.add_argument("--margin-m", type=float, default=100.0)
    a = ap.parse_args()
    reg = json.loads((ROOT / "config" / "regions" / f"{a.region}.json").read_text(encoding="utf-8"))
    out_dir = config.DATA_DIR / reg["raw_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"JEZ_hirise_soc_007_orthoMosaic_25cm_crop_{a.region}.tif"
    part = out.with_suffix(".part.tif")

    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
               GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", GDAL_HTTP_MAX_RETRY="5",
               GDAL_HTTP_RETRY_DELAY="3", VSI_CACHE="TRUE", VSI_CACHE_SIZE=str(256 * 1024 * 1024))
    with rasterio.Env(**env), rasterio.open("/vsicurl/" + SOURCE_URL) as src:
        win = source_window(src, reg["bbox"], a.margin_m)
        print(f"Source {src.width} x {src.height} px at {src.res[0]} m; crop {int(win.width)} x {int(win.height)} px "
              f"({win.width * src.res[0] / 1000:.2f} x {win.height * src.res[1] / 1000:.2f} km)", flush=True)
        prof = src.profile.copy()
        prof.update(width=int(win.width), height=int(win.height), transform=src.window_transform(win),
                    tiled=True, blockxsize=256, blockysize=256, compress="lzw", BIGTIFF="IF_SAFER")
        t0 = time.time()
        with rasterio.open(part, "w", **prof) as dst:
            for r in range(0, int(win.height), STRIP_ROWS):
                h = min(STRIP_ROWS, int(win.height) - r)
                block = src.read(1, window=Window(win.col_off, win.row_off + r, win.width, h))
                dst.write(block, 1, window=Window(0, r, int(win.width), h))
                done = (r + h) / win.height
                el = time.time() - t0
                print(f"  {done*100:5.1f}%  rows {r + h}/{int(win.height)}  {el/60:.1f} min elapsed", flush=True)
            dst.update_tags(SOURCE_URL=SOURCE_URL, SOURCE_WINDOW=f"col {win.col_off} row {win.row_off} "
                            f"w {win.width} h {win.height}", PRODUCER="USGS Astrogeology Science Center (2020)")
    os.replace(part, out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
