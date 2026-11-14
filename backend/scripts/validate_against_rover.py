"""Benchmark the route planner against Perseverance's real drives (validation, not a claim of safety).

For stretches where the rover drove fairly directly between two of its own waypoints
(rover odometry <= MAX_DETOUR x straight-line distance, length MIN_KM..MAX_KM), we plan a
route between the same two points and measure how far it stays from the rover's real track.
A straight line between the same points is the baseline: if the planner tracks the rover
more closely than a straight line does, it is reading the terrain in a way consistent with
the rover drivers' choices.

Caveats written into the output:
* A rover is not a suited human: its slope, rock and sand limits differ from ours.
* Rover drives are chosen for science and safety at the rover's scale; matching them is
  supporting evidence, not proof that a route is safe for people.

    python backend/scripts/validate_against_rover.py [region_id]
Writes data/processed/<region_id>/validation.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.eva import EvaParams  # noqa: E402
from app.geo import MARS_RADIUS_M, haversine_m  # noqa: E402
from app.region_store import get_region  # noqa: E402
from app.routing import RouteError, compute_route  # noqa: E402

MIN_KM, MAX_KM, MAX_DETOUR, MAX_SEGMENTS = 0.8, 4.0, 1.35, 12
PROFILES = ("fastest", "gentlest")


def _xy(lonlat: np.ndarray, lat0: float) -> np.ndarray:
    """Local equirectangular metres (accurate to <0.1% over a few km)."""
    lon, lat = np.radians(lonlat[:, 0]), np.radians(lonlat[:, 1])
    return np.c_[MARS_RADIUS_M * lon * math.cos(math.radians(lat0)), MARS_RADIUS_M * lat]


def _densify(line: np.ndarray, step_m: float, lat0: float) -> np.ndarray:
    xy = _xy(line, lat0)
    out = [xy[0]]
    for a, b in zip(xy[:-1], xy[1:]):
        n = max(1, int(np.hypot(*(b - a)) // step_m))
        out += [a + (b - a) * t for t in np.linspace(0, 1, n + 1)[1:]]
    return np.array(out)


def _separation(route_xy: np.ndarray, track_xy: np.ndarray) -> np.ndarray:
    """Distance from each route sample to the nearest rover-track sample (m)."""
    from scipy.spatial import cKDTree
    return cKDTree(track_xy).query(route_xy)[0]


def main() -> int:
    region_id = sys.argv[1] if len(sys.argv) > 1 else "jezero"
    reg = get_region(region_id)
    if reg is None:
        print(f"Region {region_id} is not prepared")
        return 1
    g = reg.grid
    folder = ROOT / "data" / "processed" / region_id
    raw = ROOT / "data" / "raw" / region_id
    wp_file = next(iter(sorted(raw.rglob("M20_waypoints.json"))), None)
    tr_file = next(iter(sorted(raw.rglob("M20_traverse.json"))), None)
    if not wp_file or not tr_file:
        print(f"Need the original NASA files M20_waypoints.json and M20_traverse.json in {raw}")
        return 1
    wps = json.loads(wp_file.read_text(encoding="utf-8"))["features"]
    trav = json.loads(tr_file.read_text(encoding="utf-8"))["features"]
    wps = sorted((f["properties"] for f in wps), key=lambda p: (p.get("sol", 0), p.get("site", 0), p.get("drive", 0)))
    track = [(p.get("sol", 0), c[0], c[1]) for f in trav for p in [f["properties"]]
             for c in f["geometry"]["coordinates"]]
    lat0 = (g.south + g.north) / 2

    # candidate stretches: rover drove nearly directly between waypoint i and j
    segs = []
    i = 0
    while i < len(wps) - 1 and len(segs) < MAX_SEGMENTS:
        a = wps[i]
        best = None
        for j in range(i + 1, len(wps)):
            b = wps[j]
            odo = (b.get("dist_total_m") or 0) - (a.get("dist_total_m") or 0)
            if odo > MAX_KM * 1000 * MAX_DETOUR:
                break
            sl = haversine_m(a["lon"], a["lat"], b["lon"], b["lat"])
            if MIN_KM * 1000 <= sl <= MAX_KM * 1000 and odo > 0 and odo <= MAX_DETOUR * sl \
                    and g.contains(a["lon"], a["lat"]) and g.contains(b["lon"], b["lat"]):
                best = (j, sl, odo)
        if best:
            j, sl, odo = best
            segs.append((i, j, sl, odo))
            i = j
        else:
            i += 1

    eva = EvaParams.defaults().merged({"round_trip": False, "eva_hours": 12})
    results = []
    for i, j, sl, odo in segs:
        a, b = wps[i], wps[j]
        tr = np.array([(lon, lat) for s, lon, lat in track if a["sol"] <= s <= b["sol"]])
        if len(tr) < 5:
            continue
        track_xy = _densify(tr, 5.0, lat0)
        straight = _densify(np.array([[a["lon"], a["lat"]], [b["lon"], b["lat"]]]), 5.0, lat0)
        row = {"from": {"sol": a["sol"], "rmc": a.get("RMC"), "lon": a["lon"], "lat": a["lat"]},
               "to": {"sol": b["sol"], "rmc": b.get("RMC"), "lon": b["lon"], "lat": b["lat"]},
               "straight_line_km": round(sl / 1000, 3), "rover_odometry_km": round(odo / 1000, 3),
               "baseline_straight_line": {}, "planner": {}}
        d0 = _separation(straight, track_xy)
        row["baseline_straight_line"] = {"median_m": round(float(np.median(d0)), 1),
                                         "p90_m": round(float(np.percentile(d0, 90)), 1)}
        for prof in PROFILES:
            try:
                r = compute_route(reg, [(a["lon"], a["lat"]), (b["lon"], b["lat"])], eva, prof)
            except RouteError as e:
                row["planner"][prof] = {"error": e.code}
                continue
            d = _separation(_densify(np.array(r["geometry"]["coordinates"]), 5.0, lat0), track_xy)
            row["planner"][prof] = {"distance_km": r["distance_km"], "median_m": round(float(np.median(d)), 1),
                                    "p90_m": round(float(np.percentile(d, 90)), 1),
                                    "max_grade_deg": r["max_slope_deg"]}
        results.append(row)

    def agg(key):
        vals = [r["planner"][key]["median_m"] for r in results if "median_m" in r["planner"].get(key, {})]
        base = [r["baseline_straight_line"]["median_m"] for r in results if "median_m" in r["planner"].get(key, {})]
        if not vals:
            return None
        closer = sum(v < b for v, b in zip(vals, base))
        return {"segments": len(vals), "median_of_medians_m": round(float(np.median(vals)), 1),
                "baseline_median_of_medians_m": round(float(np.median(base)), 1),
                "closer_than_straight_line": f"{closer} of {len(vals)}"}

    out = {
        "method": ("For stretches where Perseverance drove fairly directly (odometry <= "
                   f"{MAX_DETOUR}x straight line, {MIN_KM}-{MAX_KM} km), plan a route between the same two rover "
                   "waypoints and measure its distance to the rover's real track; a straight line is the baseline."),
        "summary": {p: agg(p) for p in PROFILES},
        "segments": results,
        "data": ["Perseverance waypoints and traverse (NASA/JPL MMGIS)",
                 "Region terrain: " + ", ".join(s["label"] for k, s in reg.manifest["sources"].items()
                                                if k.startswith("dem") and s.get("found"))],
        "caveats": ["A rover is not a suited human: its slope, rock and sand limits differ from the EVA limits used here.",
                    "Matching the rover's path is supporting evidence that the planner reads terrain sensibly, "
                    "not proof that any route is safe for people.",
                    "Stretches are chosen automatically by the rule above; science detours are excluded."],
    }
    (folder / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["summary"], indent=2))
    for r in results:
        p = r["planner"].get("fastest", {})
        print(f"  sol {r['from']['sol']:4d}->{r['to']['sol']:4d}  straight {r['straight_line_km']:.2f} km  rover "
              f"{r['rover_odometry_km']:.2f} km  planner {p.get('distance_km')} km  median sep planner "
              f"{p.get('median_m')} m vs straight {r['baseline_straight_line']['median_m']} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
