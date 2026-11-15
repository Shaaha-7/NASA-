"""Boulder shadows in 25 cm HiRISE imagery (EXPERIMENTAL, image-derived, not validated against ground truth).

Why: the DEMs resolve terrain at ~1-2 m, so single rocks smaller than that are invisible to slope and roughness.
HiRISE at 25 cm/px shows boulders of about 1 m and larger, mostly through the shadows they cast.

Method (the idea behind automated rock counts for Mars landing sites, e.g. Golombek et al. 2008,
JGR 113, E00A09, which detect rocks from their shadows in HiRISE images; this is a simplified version):
1. Local background: mean and standard deviation of brightness in a ~10 m window.
2. Shadow pixels: clearly darker than the local background (both a z-score and a ratio test).
3. Connected shadow blobs are kept when they are compact and rock-sized; long thin shadows (scarps, ridges,
   dune troughs) and big dark patches are rejected.
4. Each kept blob counts as one boulder; its size is the equivalent diameter of the shadow (approximate:
   shadow size depends on sun angle and rock height, which this mosaic does not give per pixel).

This is a heuristic indicator of rockiness. It does not change slope (slope comes only from the DEM), and it is
labelled experimental everywhere it is shown.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

WINDOW_M = 10.0          # local background window
Z_DARK = 2.0             # shadow: darker than mean - Z_DARK * std ...
RATIO_DARK = 0.80        # ... and darker than RATIO_DARK * mean
MIN_AREA_M2 = 0.5        # smallest shadow kept (8 px at 25 cm); below this detection is unreliable
MAX_AREA_M2 = 30.0       # bigger dark areas are not single boulders
MIN_FILL = 0.35          # blob area / bounding-box area (rejects thin curving shadows)
MAX_ELONGATION = 4.0     # long side / short side of the bounding box


def detect(img: np.ndarray, res_m: float = 0.25, nodata: int | None = 0) -> dict:
    """Detect boulder shadows in one image chunk.

    Returns centroids (row, col, float pixel coords), shadow area (m2), equivalent diameter (m), and the
    valid-pixel mask fraction. Pixels equal to `nodata` are ignored (and never counted as shadow)."""
    f = img.astype("float32")
    valid = np.ones(f.shape, bool) if nodata is None else (img != nodata)
    if valid.sum() < 100:
        return {"rows": np.empty(0), "cols": np.empty(0), "area_m2": np.empty(0), "diameter_m": np.empty(0),
                "valid_fraction": float(valid.mean())}
    w = max(3, int(round(WINDOW_M / res_m)) | 1)
    fv = np.where(valid, f, 0.0)
    n = ndimage.uniform_filter(valid.astype("float32"), w)
    n = np.maximum(n, 1e-6)
    mean = ndimage.uniform_filter(fv, w) / n
    sq = ndimage.uniform_filter(fv * fv, w) / n
    std = np.sqrt(np.maximum(sq - mean * mean, 0.0))
    shadow = valid & (n > 0.6) & (f < mean - Z_DARK * std) & (f < RATIO_DARK * mean)
    lab, nlab = ndimage.label(shadow, structure=np.ones((3, 3)))
    if nlab == 0:
        return {"rows": np.empty(0), "cols": np.empty(0), "area_m2": np.empty(0), "diameter_m": np.empty(0),
                "valid_fraction": float(valid.mean())}
    idx = np.arange(1, nlab + 1)
    area_px = ndimage.sum_labels(np.ones_like(lab, dtype="float32"), lab, idx)
    sl = ndimage.find_objects(lab)
    h = np.array([s[0].stop - s[0].start for s in sl], dtype="float32")
    wdt = np.array([s[1].stop - s[1].start for s in sl], dtype="float32")
    px_m2 = res_m * res_m
    area = area_px * px_m2
    fill = area_px / (h * wdt)
    elong = np.maximum(h, wdt) / np.maximum(np.minimum(h, wdt), 1)
    keep = (area >= MIN_AREA_M2) & (area <= MAX_AREA_M2) & (fill >= MIN_FILL) & (elong <= MAX_ELONGATION)
    if not keep.any():
        return {"rows": np.empty(0), "cols": np.empty(0), "area_m2": np.empty(0), "diameter_m": np.empty(0),
                "valid_fraction": float(valid.mean())}
    cent = np.array(ndimage.center_of_mass(shadow, lab, idx[keep]), dtype="float64").reshape(-1, 2)
    a = area[keep]
    return {"rows": cent[:, 0], "cols": cent[:, 1], "area_m2": a, "diameter_m": 2 * np.sqrt(a / np.pi),
            "valid_fraction": float(valid.mean())}
