"""Ground view: real Perseverance camera images taken where the rover stood nearest a point.

Source: NASA's Perseverance raw images gallery (an official resource of the challenge), via its
public JSON feed https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json&sol=N

* The nearest rover stop comes from the rover's own localizations (MMGIS waypoints).
* Images are those taken on the sols the rover stayed at that stop (up to MAX_SOLS sols).
* Sample-tube (CacheCam) and sky images and small sub-frames are skipped: we want the ground.
* Each sol's feed is cached in data/cache/raw_images/ so the feature works offline once fetched.

These are RAW images (not calibrated); they show the ground, they are not measurements.
"""
from __future__ import annotations

import json
import math
import re

from . import config, netutil
from .geo import haversine_m

FEED = "https://mars.nasa.gov/rss/api/"
GALLERY = "https://mars.nasa.gov/mars2020/multimedia/raw-images/"
CACHE_DIR = config.CACHE_DIR / "raw_images"
MAX_SOLS = 4
GROUND_CAMERAS = {  # instrument -> (priority, plain label)
    "MCZ_LEFT": (0, "Mastcam-Z (left), mast colour camera"),
    "MCZ_RIGHT": (1, "Mastcam-Z (right), mast colour camera"),
    "NAVCAM_LEFT": (2, "Navcam (left), navigation camera"),
    "SHERLOC_WATSON": (3, "SHERLOC WATSON, close-up of rock texture"),
    "FRONT_HAZCAM_LEFT_A": (4, "Front Hazcam, ground in front of the rover"),
    "REAR_HAZCAM_LEFT": (5, "Rear Hazcam, ground behind the rover"),
    "NAVCAM_RIGHT": (6, "Navcam (right), navigation camera"),
    "FRONT_HAZCAM_RIGHT_A": (7, "Front Hazcam (right)"),
}
MIN_SIDE_PX = 500


def _dims(ext: dict) -> tuple[int, int]:
    m = re.match(r"\((\d+),\s*(\d+)\)", str(ext.get("dimension") or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _sol_feed(sol: int, allow_fetch: bool = True) -> tuple[list[dict] | None, str]:
    """Image list for one sol: from the disk cache, else from NASA (then cached)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f = CACHE_DIR / f"sol_{sol:05d}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")), "cached"
        except Exception:
            pass
    if not allow_fetch or not netutil.is_online():
        return None, "not cached (offline)"
    try:
        r = netutil.get(FEED, {"feed": "raw_images", "category": "mars2020", "feedtype": "json", "sol": sol,
                               "num": 100, "page": 0}, timeout=40)
        images = r.json().get("images", [])
    except Exception as e:  # network or feed error: report, never invent
        return None, f"fetch failed: {str(e).splitlines()[0][:120]}"
    keep = []
    for x in images:
        inst = (x.get("camera") or {}).get("instrument")
        w, h = _dims(x.get("extended") or {})
        if inst not in GROUND_CAMERAS or min(w, h) < MIN_SIDE_PX:
            continue
        files = x.get("image_files") or {}
        keep.append({"image_id": x.get("imageid"), "sol": x.get("sol"), "camera": inst,
                     "camera_label": GROUND_CAMERAS[inst][1], "date_taken_utc": x.get("date_taken_utc"),
                     "width_px": w, "height_px": h,
                     "mast_azimuth_deg": _num((x.get("extended") or {}).get("mastAz")),
                     "mast_elevation_deg": _num((x.get("extended") or {}).get("mastEl")),
                     "small_url": files.get("small"), "medium_url": files.get("medium"),
                     "large_url": files.get("large"), "nasa_page": x.get("link"),
                     "credit": x.get("credit") or "NASA/JPL-Caltech"})
    f.write_text(json.dumps(keep), encoding="utf-8")
    return keep, "live"


def _num(v):
    try:
        x = float(v)
        return round(x, 1) if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _waypoints(region) -> list[dict]:
    fc = region.read_geojson("rover_waypoints.geojson")
    out = []
    for f in fc.get("features", []):
        p = f.get("properties", {})
        op = p.get("original_properties") or {}
        lon, lat = f["geometry"]["coordinates"][:2]
        out.append({"sol": int(p.get("sol", op.get("sol", 0))), "lon": lon, "lat": lat,
                    "rmc": op.get("RMC"), "site": op.get("site", 0), "drive": op.get("drive", 0)})
    out.sort(key=lambda w: (w["sol"], w["site"], w["drive"]))
    return out


def ground_view(region, lon: float, lat: float, max_images: int = 8, allow_fetch: bool = True) -> dict:
    wps = _waypoints(region)
    if not wps:
        return {"available": False, "reason": "No rover waypoints in this region."}
    near = min(wps, key=lambda w: haversine_m(lon, lat, w["lon"], w["lat"]))
    dist = haversine_m(lon, lat, near["lon"], near["lat"])
    # sols the rover stayed at this stop: from its arrival to the sol before the next localization
    later = [w["sol"] for w in wps if w["sol"] > near["sol"]]
    last = (min(later) - 1) if later else near["sol"]
    sols = list(range(near["sol"], min(last, near["sol"] + MAX_SOLS - 1) + 1))
    images, status = [], {}
    for s in sols:
        imgs, st = _sol_feed(s, allow_fetch)
        status[str(s)] = st
        images += imgs or []
    images.sort(key=lambda x: (GROUND_CAMERAS[x["camera"]][0], x.get("date_taken_utc") or ""))
    # one image per camera first, then fill up
    picked, seen = [], set()
    for x in images:
        if x["camera"] not in seen:
            picked.append(x)
            seen.add(x["camera"])
    picked += [x for x in images if x not in picked]
    return {
        "available": bool(picked),
        "requested": [lon, lat],
        "rover_stop": {"sol": near["sol"], "rmc": near["rmc"], "lon": near["lon"], "lat": near["lat"],
                       "distance_m": round(dist, 1)},
        "sols_searched": sols,
        "fetch_status": status,
        "images": picked[:max_images],
        "images_total": len(images),
        "source": "NASA Mars 2020 Perseverance raw images (public feed)",
        "source_url": GALLERY,
        "notes": ["Raw, uncalibrated images; NASA/JPL-Caltech credits apply to each image.",
                  "Images show the rover's surroundings on these sols, which may face away from the requested point.",
                  f"Nearest rover stop is {dist:.0f} m from the requested point."],
    }


def prefetch_for_sites(region, sites: list[dict]) -> dict:
    """Cache the image lists for every science site's nearest rover stop (call while online)."""
    report = {}
    for f in sites:
        lon, lat = f["geometry"]["coordinates"][:2]
        gv = ground_view(region, lon, lat, max_images=1)
        report[f.get("properties", {}).get("id", "?")] = {"sols": gv.get("sols_searched"),
                                                          "images": gv.get("images_total", 0)}
    return report
