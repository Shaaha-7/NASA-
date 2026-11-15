"""Rover-assisted Marswalk with an Apollo-style walk-back check.

The crew drives between stops and walks only at the stops. The rule that kept Apollo crews alive applies:
at every point of the drive, the crew must be able to WALK back to the habitat if the rover breaks down,
within the suit time they have left.

Sources (NASA Space Exploration Vehicle concept fact sheet, FS-2011-08-045-JSC,
https://www.nasa.gov/wp-content/uploads/2015/08/464826main_sev_factsheet_508.pdf):
* crew of two (four in an emergency); travels at about 10 km/h;
* suitports allow suit donning and vehicle egress in less than 10 minutes;
* "During the Apollo program, exploration was confined to the distance astronauts could expect to walk back
  wearing spacesuits if their rovers broke down: about 6 miles."
Everything else (driving on the walkers' passable terrain, the terrain slow-down, stop times) is a team
assumption and is listed in the output.

Model:
* Drive path: least-time path on the SAME passable terrain as walkers (slope and roughness limits) - a
  conservative choice, since rover climbing limits are not in the fact sheet.
* Drive time: step length / rover speed x the same roughness and geologic-unit multiplier as walking.
* Walk-back time from any cell: Dijkstra on the walking model, from the cell back to the habitat (signed grade).
* Walk-back limit: pressurized rover -> a fresh suit: usable EVA minutes minus one suitport exit;
  unpressurized rover -> the crew is suited all along: usable minutes minus suit time already used.
"""
from __future__ import annotations

import math
import time

import numpy as np

from .eva import EvaParams
from .geo import haversine_m
from .reachability import _dijkstra
from .region_store import Region
from .routing import RouteError, _simplify, astar, build_masks, compute_route, snap

SEV_FACTSHEET = "https://www.nasa.gov/wp-content/uploads/2015/08/464826main_sev_factsheet_508.pdf"


def _path(region: Region, passable, mult, cells: list[int], eva: EvaParams) -> tuple[np.ndarray, list[int]]:
    parts, bounds = [], [0]
    for k in range(len(cells) - 1):
        a, b = cells[k], cells[k + 1]
        part = np.array([a], dtype=np.int64) if a == b else astar(region, passable, mult, a, b, eva, "fastest")[0]
        if part.size == 0:
            raise RouteError(f"No drivable path for leg {k + 1} on terrain within the slope and roughness limits",
                             "no_route", {"leg": k + 1})
        if parts:
            part = part[1:]
        parts.append(part)
        bounds.append(sum(len(p) for p in parts) - 1)
    return np.concatenate(parts), bounds


def _steps(region: Region, cells: np.ndarray, mult: np.ndarray):
    W = region.grid.width
    rows, cols = cells // W, cells % W
    dxm = 0.5 * (region.dx_rows[rows[:-1]] + region.dx_rows[rows[1:]]) * np.diff(cols)
    dym = region.grid.dy_m * np.diff(rows)
    d = np.hypot(dxm, dym)
    m = 0.5 * (mult[cells[:-1]] + mult[cells[1:]])
    return d, m


def _envelope_geojson(region: Region, mask2d: np.ndarray, min_cells: int = 12) -> dict:
    from rasterio import features
    m = features.sieve(mask2d.astype("uint8"), size=min_cells, connectivity=8)
    polys = [[[[round(x, 6), round(y, 6)] for x, y in ring] for ring in geom["coordinates"]]
             for geom, val in features.shapes(m, mask=m.astype(bool), transform=region.grid.affine(), connectivity=8)
             if val == 1]
    feats = [{"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": polys},
              "properties": {"meaning": "Walk-back envelope: the crew can walk home from here within a fresh suit's usable time",
                             "measured_or_derived": "model estimate (team EVA assumptions)"}}] if polys else []
    return {"type": "FeatureCollection", "features": feats}


def compute_rover_plan(region: Region, points: list[tuple[float, float]], eva: EvaParams, names: list[str],
                       rover_type: str = "pressurized", speed_kmh: float = 10.0, stop_minutes: float = 30.0,
                       suitport_minutes: float = 10.0) -> dict:
    if len(points) < 2:
        raise RouteError("Need at least a start (habitat) and a destination", "bad_request")
    t0 = time.perf_counter()
    g = region.grid
    W = g.width
    passable, mult = build_masks(region, eva)
    snapped = [snap(region, passable, lon, lat) for lon, lat in points]
    cells = [c for c, _ in snapped]
    home = cells[0]

    out_cells, out_bounds = _path(region, passable, mult, cells, eva)
    back_cells, _ = _path(region, passable, mult, [cells[-1], home], eva)
    v = speed_kmh / 3.6
    d_out, m_out = _steps(region, out_cells, mult)
    d_back, m_back = _steps(region, back_cells, mult)
    drive_out_s = d_out / v * m_out
    drive_back_s = d_back / v * m_back

    # walk-back time from every cell to the habitat (walking model, signed grade)
    usable_s = eva.usable_minutes * 60.0
    t_home = _dijkstra(region.elev_flat, passable, mult, g.height, g.width, region.dx_rows, g.dy_m, int(home),
                       eva.flat_speed_ms, eva.max_grade, True, usable_s * 4)
    t_home = np.where(t_home < 1e299, t_home, np.inf)

    n_eva_stops = len(points) - 1          # every stop after the habitat, destination included
    per_stop_s = (stop_minutes + 2 * suitport_minutes) * 60.0
    fresh_limit_s = usable_s - suitport_minutes * 60.0

    # timeline along the whole sortie: outbound drive with stops, then the drive home
    seq_cells = np.concatenate([out_cells, back_cells[1:]])
    step_s = np.concatenate([drive_out_s, drive_back_s])
    step_d = np.concatenate([d_out, d_back])
    stop_at = set(out_bounds[1:])           # path indices where an EVA stop happens
    elapsed = np.zeros(len(seq_cells))      # mission clock at each path point (s)
    suit_used = np.zeros(len(seq_cells))    # suit time already used (unpressurized only)
    clock = suit = 0.0
    for i in range(len(seq_cells)):
        if i > 0:
            clock += step_s[i - 1]
            suit += step_s[i - 1]
        elapsed[i] = clock
        suit_used[i] = suit
        if i in stop_at:
            clock += per_stop_s
            suit += stop_minutes * 60.0
    limit = np.full(len(seq_cells), fresh_limit_s) if rover_type == "pressurized" else usable_s - suit_used
    walkback = t_home[seq_cells]
    margin = limit - walkback
    cum_d = np.concatenate([[0.0], np.cumsum(step_d)])

    lonlat = [g.center_of(int(c) // W, int(c) % W) for c in seq_cells]
    bad = ~(margin >= 0)
    warnings = []
    i = 0
    while i < len(bad) and len(warnings) < 8:
        if bad[i]:
            j = i
            while j + 1 < len(bad) and bad[j + 1]:
                j += 1
            seg = slice(i, j + 1)
            worst = int(i + np.argmin(np.nan_to_num(margin[seg], neginf=-1e9)))
            wb = walkback[worst]
            mid = (i + j) // 2
            warnings.append({
                "rule_id": "R8_WALKBACK", "severity": "warning",
                "title": "Beyond walk-back range" if np.isfinite(wb) else "No walking path home",
                "explanation": (f"If the rover failed here, walking home would take {wb / 60:.0f} min but only "
                                f"{max(limit[worst], 0) / 60:.0f} min of suit time would be left." if np.isfinite(wb) else
                                "No walking path back to the habitat exists within the slope and roughness limits."),
                "rule": "walk-back time to habitat <= suit time available (Apollo walk-back rule)",
                "value": round(float(wb) / 60, 1) if np.isfinite(wb) else None, "unit": "min",
                "threshold": round(float(max(limit[worst], 0)) / 60, 1),
                "location": [round(lonlat[mid][0], 6), round(lonlat[mid][1], 6)],
                "at_distance_km": round(float(cum_d[mid]) / 1000, 3),
                "length_m": round(float(cum_d[j] - cum_d[i]), 0),
                "data_basis": ["Walking model (team EVA assumptions)", "NASA SEV concept fact sheet (walk-back rule)"],
                "measured_or_derived": "model estimate"})
            i = j + 1
        else:
            i += 1

    drive_out_min = float(drive_out_s.sum() / 60)
    drive_back_min = float(drive_back_s.sum() / 60)
    stops_min = n_eva_stops * per_stop_s / 60
    total_min = drive_out_min + stops_min + drive_back_min
    longest_suit_min = (stop_minutes + suitport_minutes) if rover_type == "pressurized" else float(suit_used[-1] / 60)
    finite = np.isfinite(walkback)

    # walking-only plan for the same stops, for comparison
    try:
        walk = compute_route(region, points, eva, "fastest", names)
        # same work time at every stop as the rover plan, so the two are compared like for like;
        # walking, the crew is in the suit for the whole sortie
        suit_min = walk["eva"]["required_min"] + n_eva_stops * stop_minutes
        walking = {"walking_min": walk["eva"]["required_min"], "stop_work_min": round(n_eva_stops * stop_minutes, 1),
                   "total_min": round(suit_min, 1), "longest_suit_time_min": round(suit_min, 1),
                   "within_budget": bool(suit_min <= eva.usable_minutes), "distance_km": walk["distance_km"],
                   "round_trip": eva.round_trip}
    except RouteError as e:
        walking = {"error": str(e)}

    step = max(1, len(seq_cells) // 300)
    sel = list(range(0, len(seq_cells), step)) + ([len(seq_cells) - 1] if (len(seq_cells) - 1) % step else [])
    prof = [{"distance_km": round(float(cum_d[k]) / 1000, 3), "elapsed_min": round(float(elapsed[k]) / 60, 1),
             "walkback_min": round(float(walkback[k]) / 60, 1) if np.isfinite(walkback[k]) else None,
             "limit_min": round(float(max(limit[k], 0)) / 60, 1)} for k in sel]

    def line(cs):
        keep = _simplify(cs, W, set())
        return [[round(x, 7) for x in g.center_of(int(cs[i]) // W, int(cs[i]) % W)] for i in keep]

    stops = []
    for k, (lon, lat) in enumerate(points):
        pi = out_bounds[k]
        stops.append({"name": names[k] if k < len(names) and names[k] else ("Habitat" if k == 0 else f"Stop {k}"),
                      "snapped": [round(lonlat[pi][0], 6), round(lonlat[pi][1], 6)],
                      "snapped_m": round(float(snapped[k][1]), 1),
                      "arrive_min": round(float(elapsed[pi]) / 60, 1),
                      "walkback_min": round(float(walkback[pi]) / 60, 1) if np.isfinite(walkback[pi]) else None,
                      "straight_line_home_km": round(haversine_m(*points[0], *points[k]) / 1000, 3)})

    env_mask = (t_home <= fresh_limit_s).reshape(g.height, g.width)
    return {
        "region_id": region.region_id,
        "is_test_fixture": region.is_test_fixture,
        "mode": "rover-assisted",
        "rover": {"type": rover_type, "speed_kmh": speed_kmh, "stop_minutes": stop_minutes,
                  "suitport_minutes": suitport_minutes, "crew_size": eva.crew_size},
        "geometry": {"type": "MultiLineString", "coordinates": [line(out_cells), line(back_cells)]},
        "stops": stops,
        "drive_km": round(float(cum_d[-1]) / 1000, 3),
        "drive_out_min": round(drive_out_min, 1),
        "drive_back_min": round(drive_back_min, 1),
        "eva_at_stops_min": round(stops_min, 1),
        "total_min": round(total_min, 1),
        "longest_suit_time_min": round(longest_suit_min, 1),
        "suit_time_within_budget": bool(longest_suit_min <= eva.usable_minutes),
        "walkback": {
            "rule": "At every point of the drive the crew must be able to walk home if the rover fails "
                    "(Apollo walk-back rule, NASA SEV fact sheet).",
            "limit_basis": ("fresh suit: usable EVA time minus one suitport exit" if rover_type == "pressurized"
                            else "suit time left: usable EVA time minus suit time already used"),
            "max_walkback_min": round(float(walkback[finite].max()) / 60, 1) if finite.any() else None,
            "min_margin_min": round(float(np.nanmin(np.where(np.isfinite(margin), margin, -np.inf))) / 60, 1)
            if np.isfinite(margin).any() else None,
            "fraction_within": round(float((margin >= 0).mean()), 3),
            "ok": bool((margin >= 0).all()),
            "profile": prof,
        },
        "walkback_envelope": _envelope_geojson(region, env_mask),
        "walking_only": walking,
        "warnings": warnings,
        "eva_params": eva.as_dict(),
        "assumptions": [
            f"Rover speed {speed_kmh:g} km/h on flat smooth ground (NASA SEV concept: about 10 km/h), slowed by the same "
            "roughness and geologic-unit multipliers as walking - team assumption.",
            "The rover drives only on terrain within the walkers' slope and roughness limits (conservative; rover "
            "climbing limits are not given in the SEV fact sheet).",
            f"Each stop: {stop_minutes:g} min of EVA work plus suitport exit and entry of {suitport_minutes:g} min each "
            "(NASA SEV concept: under 10 min) - team assumption for the work time.",
            ("Pressurized rover: the crew rides in the cabin, so each stop uses a fresh suit; if the rover fails they "
             "exit once and walk home." if rover_type == "pressurized" else
             "Unpressurized rover: the crew stays suited for the whole sortie, so suit time is used while driving."),
        ] + eva.assumptions(),
        "limitations": ["Model estimate under team assumptions, not a certified traverse plan.",
                        "Rover power, communication range and a second rescue rover are not modelled "
                        "(the SEV fact sheet notes two rovers would extend the safe range).",
                        f"Terrain resolved at {g.mean_res_m:.0f} m; smaller obstacles are not seen."],
        "sources": [{"label": "NASA Space Exploration Vehicle concept fact sheet (FS-2011-08-045-JSC)", "url": SEV_FACTSHEET}],
        "compute_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
