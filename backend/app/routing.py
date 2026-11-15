"""Terrain-aware Marswalk routing.

* A* on the processed terrain grid, 8-connected.
* The cost of a step is the modelled WALKING TIME: horizontal step length divided by the
  Tobler speed for the step's signed grade, times terrain multipliers (roughness, geologic unit).
  Uphill and downhill therefore cost differently, and crossing a slope sideways is cheaper
  than climbing it.
* Steps steeper than the EVA grade limit, and cells steeper/rougher than the limits, are excluded.
* The heuristic (straight-line distance / fastest possible speed) never overestimates, so A*
  returns the least-cost path on the grid.
* Profiles: "fastest" (time), "gentlest" (time + strong penalty on grade), "shortest" (distance).
"""
from __future__ import annotations

import heapq
import math
import time
import uuid

import numpy as np
from scipy import ndimage

from .eva import EvaParams, TOBLER_K, TOBLER_OPT
from . import directions
from .geo import MARS_RADIUS_M, Grid, haversine_m
from .region_store import Region

try:  # numba makes A* ~50x faster; the pure-Python path gives identical results.
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False

    def njit(*a, **k):
        def wrap(f):
            return f
        return wrap if not (a and callable(a[0])) else a[0]


PROFILES = {
    "fastest": {"mode": 0, "grade_weight": 0.0, "label": "Fastest (least modelled walking time)"},
    "gentlest": {"mode": 0, "grade_weight": 2.0, "label": "Gentlest (time plus a strong penalty on steep grades)"},
    "shortest": {"mode": 1, "grade_weight": 0.0, "label": "Shortest (least horizontal distance within the EVA limits)"},
}


class RouteError(Exception):
    def __init__(self, message: str, code: str = "no_route", detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def _astar_impl(elev, passable, mult, H, W, dx_rows, dy, start, goal, v_flat, max_grade, mode,
                grade_weight, caution_grade):
    n = H * W
    INF = 1e300
    g_cost = np.full(n, INF)
    came = np.full(n, -1, dtype=np.int64)
    closed = np.zeros(n, dtype=np.bool_)
    norm = math.exp(-TOBLER_K * TOBLER_OPT)
    vmax = v_flat / norm
    dx_min = dx_rows.min()
    gr = goal // W
    gc = goal % W
    g_cost[start] = 0.0
    heap = [(0.0, np.int64(start))]
    drs = (-1, -1, -1, 0, 0, 1, 1, 1)
    dcs = (-1, 0, 1, -1, 1, -1, 0, 1)
    while len(heap) > 0:
        f, cur = heapq.heappop(heap)
        if closed[cur]:
            continue
        if cur == goal:
            break
        closed[cur] = True
        r = cur // W
        c = cur % W
        zc = elev[cur]
        for k in range(8):
            nr = r + drs[k]
            nc = c + dcs[k]
            if nr < 0 or nr >= H or nc < 0 or nc >= W:
                continue
            nb = nr * W + nc
            if closed[nb] or not passable[nb]:
                continue
            dxm = 0.5 * (dx_rows[r] + dx_rows[nr]) * dcs[k]
            dym = dy * drs[k]
            d = math.sqrt(dxm * dxm + dym * dym)
            grade = (elev[nb] - zc) / d
            if abs(grade) > max_grade:
                continue
            if mode == 1:
                step = d
            else:
                v = v_flat * math.exp(-TOBLER_K * abs(grade + TOBLER_OPT)) / norm
                step = d / v * 0.5 * (mult[cur] + mult[nb])
                if grade_weight > 0.0:
                    q = grade / caution_grade
                    step *= 1.0 + grade_weight * q * q
            ng = g_cost[cur] + step
            if ng < g_cost[nb]:
                g_cost[nb] = ng
                came[nb] = cur
                hx = (gc - nc) * dx_min
                hy = (gr - nr) * dy
                h = math.sqrt(hx * hx + hy * hy)
                if mode == 0:
                    h = h / vmax
                heapq.heappush(heap, (ng + h, np.int64(nb)))
    if g_cost[goal] >= INF:
        return np.empty(0, dtype=np.int64), INF
    # reconstruct
    count = 1
    p = goal
    while p != start:
        p = came[p]
        count += 1
    path = np.empty(count, dtype=np.int64)
    p = goal
    i = count - 1
    while True:
        path[i] = p
        if p == start:
            break
        p = came[p]
        i -= 1
    return path, g_cost[goal]


_astar_fast = njit(cache=True)(_astar_impl) if HAVE_NUMBA else _astar_impl


def astar(region: Region, passable: np.ndarray, mult: np.ndarray, start: int, goal: int, eva: EvaParams,
          profile: str):
    pr = PROFILES[profile]
    g = region.grid
    path, cost = _astar_fast(region.elev_flat, passable, mult, g.height, g.width, region.dx_rows, g.dy_m,
                             int(start), int(goal), eva.flat_speed_ms, eva.max_grade, pr["mode"],
                             pr["grade_weight"], math.tan(math.radians(eva.caution_slope_deg)))
    return path, cost

# ------------------------------------------------------------------ helpers


def build_masks(region: Region, eva: EvaParams):
    elev = region.elev_flat
    slope = region.slope_flat
    rough = region.rough_flat
    finite = np.isfinite(elev)
    rough0 = np.where(np.isfinite(rough), rough, 0.0)
    passable = finite & (np.nan_to_num(slope, nan=90.0) <= eva.max_slope_deg) & (rough0 <= eva.roughness_max_m)
    mult = (1.0 + rough0 / eva.roughness_ref_m) * region.unit_mult_flat
    return passable, mult


def snap(region: Region, passable: np.ndarray, lon: float, lat: float, max_snap_m: float = 250.0):
    g = region.grid
    if not g.contains(lon, lat):
        raise RouteError(f"Point ({lon:.5f}, {lat:.5f}) is outside region '{region.region_id}' "
                         f"[{g.west:.4f}..{g.east:.4f} E, {g.south:.4f}..{g.north:.4f} N]", "outside_region")
    r, c = g.cell_of(lon, lat)
    idx = r * g.width + c
    if passable[idx]:
        return idx, 0.0
    blocked = ~passable.reshape(g.height, g.width)
    _, (ir, ic) = ndimage.distance_transform_edt(blocked, sampling=(g.dy_m, float(region.dx_rows.mean())),
                                                 return_indices=True)
    nr, nc = int(ir[r, c]), int(ic[r, c])
    lon2, lat2 = g.center_of(nr, nc)
    d = haversine_m(lon, lat, lon2, lat2)
    if d > max_snap_m:
        raise RouteError(f"No walkable terrain within {max_snap_m:.0f} m of ({lon:.5f}, {lat:.5f}) "
                         f"under the current EVA limits", "no_walkable_terrain", {"nearest_m": round(d, 1)})
    return nr * g.width + nc, d


def _runs(mask: np.ndarray, max_gap: int = 2):
    """Contiguous True runs in a 1-D mask (small gaps merged). Yields (start, end_inclusive)."""
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    runs = []
    s = p = idx[0]
    for i in idx[1:]:
        if i - p > max_gap + 1:
            runs.append((s, p))
            s = i
        p = i
    runs.append((s, p))
    return runs


def _simplify(cells: np.ndarray, W: int, keep: set[int]) -> list[int]:
    """Drop cells where the walking direction does not change (collinear)."""
    if len(cells) <= 2:
        return list(range(len(cells)))
    out = [0]
    for i in range(1, len(cells) - 1):
        a, b, c = cells[i - 1], cells[i], cells[i + 1]
        d1 = (b // W - a // W, b % W - a % W)
        d2 = (c // W - b // W, c % W - b % W)
        if d1 != d2 or i in keep:
            out.append(i)
    out.append(len(cells) - 1)
    return out

# ------------------------------------------------------------------ stop order


MAX_OPTIMISE_STOPS = 7


def optimise_stop_order(region: Region, points: list[tuple[float, float]], eva: EvaParams,
                        profile: str = "fastest") -> dict:
    """Best visiting order for the intermediate stops (start and destination stay fixed).
    Builds a matrix of A* costs between every pair of points under the same profile and EVA
    limits, then checks every permutation (exact for up to MAX_OPTIMISE_STOPS stops)."""
    import itertools
    stops = len(points) - 2
    if stops < 2:
        return {"order": list(range(stops)), "changed": False}
    if stops > MAX_OPTIMISE_STOPS:
        raise RouteError(f"Stop-order optimisation supports up to {MAX_OPTIMISE_STOPS} stops", "bad_request")
    passable, mult = build_masks(region, eva)
    cells = [snap(region, passable, lon, lat)[0] for lon, lat in points]
    n = len(points)
    INF = float("inf")
    cost = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j or j == 0 or i == n - 1 or (i == 0 and j == n - 1):
                continue
            path, c = astar(region, passable, mult, cells[i], cells[j], eva, profile)
            cost[i][j] = c if path.size else INF
    mids = list(range(1, n - 1))

    def total(order):
        seq = [0, *order, n - 1]
        return sum(cost[a][b] for a, b in zip(seq, seq[1:]))
    best = min(itertools.permutations(mids), key=total)
    as_given = total(mids)
    if total(best) == INF:
        raise RouteError("No order of the stops is walkable under the current EVA limits", "no_route")
    unit = "min" if PROFILES[profile]["mode"] == 0 else "m"
    scale = 1 / 60 if unit == "min" else 1.0
    return {"order": [k - 1 for k in best], "changed": list(best) != mids,
            "cost_as_given": None if as_given == INF else round(as_given * scale, 1),
            "cost_optimised": round(total(best) * scale, 1), "cost_unit": unit}

# ------------------------------------------------------------------ main entry


def compute_route(region: Region, points: list[tuple[float, float]], eva: EvaParams, profile: str = "fastest",
                  stop_names: list[str] | None = None) -> dict:
    if profile not in PROFILES:
        raise RouteError(f"Unknown profile '{profile}'. Use one of {list(PROFILES)}", "bad_profile")
    if len(points) < 2:
        raise RouteError("Need at least a start and a destination", "bad_request")
    t0 = time.perf_counter()
    g = region.grid
    W = g.width
    passable, mult = build_masks(region, eva)
    snapped, cells_idx = [], []
    for (lon, lat) in points:
        idx, d = snap(region, passable, lon, lat)
        cells_idx.append(idx)
        snapped.append(d)

    path_parts, leg_bounds = [], []
    for k in range(len(cells_idx) - 1):
        a, b = cells_idx[k], cells_idx[k + 1]
        if a == b:
            part = np.array([a], dtype=np.int64)
        else:
            part, cost = astar(region, passable, mult, a, b, eva, profile)
            if part.size == 0:
                lab, _ = ndimage.label(passable.reshape(g.height, g.width), structure=np.ones((3, 3)))
                la, lb = lab.ravel()[a], lab.ravel()[b]
                if la != lb:
                    small = min(int((lab == la).sum()), int((lab == lb).sum())) * g.dy_m * float(region.dx_rows.mean())
                    raise RouteError(f"Leg {k+1}: one end lies in an area completely enclosed by terrain steeper than "
                                     f"{eva.max_slope_deg:g} deg or rougher than {eva.roughness_max_m:g} m "
                                     f"(enclosed walkable area ~{small/1e6:.2f} km2). Move the point or relax the limits.",
                                     "enclosed", {"leg": k + 1})
                raise RouteError(f"No walkable route for leg {k+1} under the current EVA limits "
                                 f"(max grade {eva.max_slope_deg:g} deg, max roughness {eva.roughness_max_m:g} m). "
                                 "Try relaxing the limits or moving the point.", "no_route", {"leg": k + 1})
        if path_parts:
            part = part[1:]
        start_i = sum(len(p) for p in path_parts)
        path_parts.append(part)
        leg_bounds.append((max(start_i - 1, 0) if k else 0, start_i + len(part) - 1))
    cells = np.concatenate(path_parts)

    # ---- per-step metrics, always in the time model so profiles are comparable
    rows, cols = cells // W, cells % W
    z = region.elev_flat[cells]
    dxm = 0.5 * (region.dx_rows[rows[:-1]] + region.dx_rows[rows[1:]]) * np.diff(cols)
    dym = g.dy_m * np.diff(rows)
    d = np.hypot(dxm, dym)
    dz = np.diff(z)
    grade = np.divide(dz, d, out=np.zeros_like(dz), where=d > 0)
    m_step = 0.5 * (mult[cells[:-1]] + mult[cells[1:]])
    norm = math.exp(-TOBLER_K * TOBLER_OPT)
    v_out = eva.flat_speed_ms * np.exp(-TOBLER_K * np.abs(grade + TOBLER_OPT)) / norm
    v_back = eva.flat_speed_ms * np.exp(-TOBLER_K * np.abs(-grade + TOBLER_OPT)) / norm
    t_out = np.divide(d, v_out) * m_step
    t_back = np.divide(d, v_back) * m_step
    cum_d = np.concatenate([[0.0], np.cumsum(d)])
    cum_t = np.concatenate([[0.0], np.cumsum(t_out)])
    total_d = float(cum_d[-1])
    out_min = float(cum_t[-1] / 60)
    back_min = float(t_back.sum() / 60)
    need_min = out_min + (back_min if eva.round_trip else 0.0)
    grade_deg = np.degrees(np.arctan(np.abs(grade)))
    slope_cells = region.slope_flat[cells]
    rough_cells = region.rough_flat[cells]

    lonlat = [g.center_of(int(r), int(c)) for r, c in zip(rows, cols)]
    stops = []
    names = stop_names or []
    for k, (lon, lat) in enumerate(points):
        pi = 0 if k == 0 else leg_bounds[k - 1][1]
        nm = names[k] if k < len(names) and names[k] else ("Start" if k == 0 else ("Destination" if k == len(points) - 1 else f"Stop {k}"))
        stops.append({"name": nm, "requested": [lon, lat], "snapped": [round(lonlat[pi][0], 6), round(lonlat[pi][1], 6)],
                      "snapped_m": round(float(snapped[k]), 1), "at_distance_km": round(float(cum_d[pi]) / 1000, 3),
                      "eta_min": round(float(cum_t[pi]) / 60, 1)})
    legs = []
    for k, (a, b) in enumerate(leg_bounds):
        legs.append({"from": stops[k]["name"], "to": stops[k + 1]["name"],
                     "distance_km": round(float(cum_d[b] - cum_d[a]) / 1000, 3),
                     "duration_min": round(float(cum_t[b] - cum_t[a]) / 60, 1)})

    # ---- elevation profile (<= 400 samples)
    step = max(1, len(cells) // 400)
    sel = list(range(0, len(cells), step))
    if sel[-1] != len(cells) - 1:
        sel.append(len(cells) - 1)
    # walking time from each point back to the start along the same path (signed grade reversed)
    cum_back = np.concatenate([[0.0], np.cumsum(t_back)])
    profile_pts = [{"distance_km": round(float(cum_d[i]) / 1000, 4), "elevation_m": round(float(z[i]), 2),
                    "grade_deg": round(float(grade_deg[min(i, len(grade_deg) - 1)]), 1) if len(grade_deg) else 0.0,
                    "eta_min": round(float(cum_t[i]) / 60, 2), "walk_home_min": round(float(cum_back[i]) / 60, 2),
                    "lon": round(lonlat[i][0], 6), "lat": round(lonlat[i][1], 6)} for i in sel]

    warnings = _warnings(region, eva, cells, lonlat, cum_d, grade_deg, rough_cells, need_min, out_min, back_min, stops)

    # turn-by-turn EVA directions from the same arrays as the metrics
    unit_table = {u["code"]: u["name"] for u in region.manifest.get("units", [])}
    unit_names = [unit_table.get(int(u)) for u in region.units_flat[cells]]
    try:
        sites = region.read_geojson("science_sites.geojson").get("features", [])
    except Exception:
        sites = []
    try:
        steps = directions.build(lonlat, cum_d, cum_t, z, grade_deg, unit_names, [b for _, b in leg_bounds],
                                 [s["name"] for s in stops], sites, warnings, MARS_RADIUS_M)
    except Exception as e:  # directions are an add-on: never fail the route because of them
        steps = [{"step": 0, "instruction": f"Directions unavailable: {e}"}]

    keep = {b for _, b in leg_bounds}
    simp = _simplify(cells, W, keep)
    coords = [[round(lonlat[i][0], 7), round(lonlat[i][1], 7)] for i in simp]

    dem_used = sorted({int(x) for x in np.unique(region.dem_source_flat[cells]) if x > 0})
    srcs = region.manifest["sources"]
    data_sources = []
    for code, key in ((1, "dem_primary"), (2, "dem_fallback")):
        if code in dem_used and srcs.get(key, {}).get("found"):
            s = srcs[key]
            data_sources.append({"role": "elevation" + (" (fallback)" if code == 2 else ""), "label": s["label"],
                                 "mission": s["mission"], "instrument": s["instrument"], "url": s["source_url"],
                                 "file": s.get("file")})
    if region.manifest.get("units") and srcs.get("geo_units", {}).get("found"):
        s = srcs["geo_units"]
        data_sources.append({"role": "geologic units (terrain multipliers)", "label": s["label"],
                             "mission": s["mission"], "instrument": s["instrument"], "url": s["source_url"],
                             "file": s.get("file")})

    finite_z = z[np.isfinite(z)]
    result = {
        "route_id": f"route-{uuid.uuid4().hex[:8]}",
        "region_id": region.region_id,
        "is_test_fixture": region.is_test_fixture,
        "profile": profile,
        "profile_label": PROFILES[profile]["label"],
        "geometry": {"type": "LineString", "coordinates": coords},
        "stops": stops,
        "legs": legs,
        "distance_km": round(total_d / 1000, 3),
        "straight_line_km": round(sum(haversine_m(*points[i], *points[i + 1]) for i in range(len(points) - 1)) / 1000, 3),
        "duration_min": round(out_min, 1),
        "return_duration_min": round(back_min, 1),
        "eva": {"required_min": round(need_min, 1), "usable_min": round(eva.usable_minutes, 1),
                "budget_min": round(eva.eva_hours * 60, 1), "within_budget": bool(need_min <= eva.usable_minutes),
                "round_trip": eva.round_trip, "estimate": True},
        "max_slope_deg": round(float(grade_deg.max()), 1) if len(grade_deg) else 0.0,
        "mean_slope_deg": round(float(np.average(grade_deg, weights=d)), 1) if len(d) and d.sum() > 0 else 0.0,
        "max_terrain_slope_deg": round(float(np.nanmax(slope_cells)), 1),
        "max_roughness_m": round(float(np.nanmax(rough_cells)), 2) if np.isfinite(rough_cells).any() else None,
        "ascent_m": round(float(dz[dz > 0].sum()), 1),
        "descent_m": round(float(-dz[dz < 0].sum()), 1),
        "elevation_min_m": round(float(finite_z.min()), 1),
        "elevation_max_m": round(float(finite_z.max()), 1),
        "elevation_profile": profile_pts,
        "directions": steps,
        "warnings": warnings,
        "data_sources": data_sources,
        "grid_resolution_m": round(g.mean_res_m, 1),
        "eva_params": eva.as_dict(),
        "assumptions": ["Prototype terrain-cost model: least modelled walking time on a "
                        f"{g.mean_res_m:.0f} m grid (A*, 8 directions)."] + eva.assumptions(),
        "limitations": [
            "Not a certified astronaut navigation or safety route; scores are relative.",
            f"Terrain is resolved at {g.mean_res_m:.0f} m (roughness from ~{region.manifest.get('fine_resolution_m', g.mean_res_m):.0f} m): "
            "individual rocks smaller than that are not seen.",
            "No live conditions: terrain data has a fixed date; dust, lighting and radiation are not in the route cost.",
            "Times and distances are model estimates, not measurements.",
        ],
        "compute_ms": round((time.perf_counter() - t0) * 1000, 1),
        "engine": "A* (numba)" if HAVE_NUMBA else "A* (pure Python)",
    }
    if region.is_test_fixture:
        result["limitations"].insert(0, "TEST FIXTURE: synthetic terrain, not real Mars data.")
    return result


def _warnings(region: Region, eva: EvaParams, cells, lonlat, cum_d, grade_deg, rough_cells, need_min, out_min,
              back_min, stops) -> list[dict]:
    W = []
    dem_label = region.manifest["sources"].get("dem_primary", {}).get("label") or \
        region.manifest["sources"].get("dem_fallback", {}).get("label")

    def add(rule_id, severity, title, explanation, rule, value, unit, threshold, i0, i1, basis, kind):
        mid = (i0 + i1) // 2
        W.append({"id": f"w{len(W)+1:02d}", "rule_id": rule_id, "severity": severity, "title": title,
                  "explanation": explanation, "rule": rule, "value": value, "unit": unit, "threshold": threshold,
                  "location": [round(lonlat[mid][0], 6), round(lonlat[mid][1], 6)],
                  "at_distance_km": round(float(cum_d[mid]) / 1000, 3),
                  "length_m": round(float(cum_d[min(i1 + 1, len(cum_d) - 1)] - cum_d[i0]), 0),
                  "data_basis": basis, "measured_or_derived": kind})

    # R1 steep grades
    for a, b in _runs(grade_deg > eva.caution_slope_deg)[:10]:
        mx = float(grade_deg[a:b + 1].max())
        sev = "warning" if mx > (eva.caution_slope_deg + eva.max_slope_deg) / 2 else "caution"
        add("R1_STEEP_GRADE", sev, f"Steep section up to {mx:.0f} deg",
            f"The route climbs or descends grades above {eva.caution_slope_deg:g} deg here. Footing and suit mobility "
            "are harder; consider the 'gentlest' profile.",
            f"grade along route > {eva.caution_slope_deg:g} deg (caution) ; limit {eva.max_slope_deg:g} deg",
            round(mx, 1), "deg", eva.caution_slope_deg, a, b + 1,
            [f"Slope from numerical elevation ({dem_label})"], "model-derived from numerical elevation")
    # R2 rough terrain
    r = np.nan_to_num(rough_cells, nan=0.0)
    for a, b in _runs(r > eva.roughness_caution_m)[:10]:
        mx = float(r[a:b + 1].max())
        add("R2_ROUGH", "caution", f"Rough ground (roughness {mx:.2f} m)",
            "Local relief here suggests blocks, ridges or a scarp edge at DEM scale. Check imagery before committing.",
            f"roughness > {eva.roughness_caution_m:g} m", round(mx, 2), "m", eva.roughness_caution_m, a, b,
            [f"Detrended RMS height from {dem_label}"], "model-derived from numerical elevation")
    # R3 soft sand / flagged units
    units = region.units_flat[cells]
    flagged = {u["code"]: u for u in region.manifest.get("units", []) if u.get("flag")}
    for code, u in flagged.items():
        for a, b in _runs(units == code)[:5]:
            add("R3_GEOLOGIC_UNIT", "caution" if u["flag"] == "soft_sand" else "info",
                f"Crosses '{u['name']}'", f"{u['reason']}. Walking time in this unit is multiplied by {u['multiplier']:g}.",
                f"geologic unit flagged '{u['flag']}' in config/geo_penalties.json", u["multiplier"], "x time", None,
                a, b, [region.manifest["sources"].get("geo_units", {}).get("label", "geologic map")],
                "interpreted (geologic map) + team assumption")
    # R4 lower-resolution elevation
    ds = region.dem_source_flat[cells]
    if region.manifest["sources"].get("dem_primary", {}).get("found"):
        for a, b in _runs(ds == 2)[:5]:
            add("R4_LOW_RES_DEM", "info", "Lower-resolution terrain data",
                "The high-resolution DEM does not cover this stretch; slope and roughness come from the coarser DEM, "
                "so small obstacles may be missed.", "elevation from fallback DEM", None, None, None, a, b,
                [region.manifest["sources"].get("dem_fallback", {}).get("label", "fallback DEM")], "data coverage")
    # R5 EVA budget
    end = len(cells) - 1
    if need_min > eva.usable_minutes:
        add("R5_EVA_BUDGET", "warning", "Exceeds the EVA time budget",
            f"Modelled time {need_min:.0f} min ({out_min:.0f} out" + (f" + {back_min:.0f} back" if eva.round_trip else "")
            + f") is more than the usable {eva.usable_minutes:.0f} min ({eva.eva_hours:g} h minus "
            f"{eva.reserve_fraction*100:.0f}% reserve).", "required time > EVA budget minus reserve",
            round(need_min, 1), "min", round(eva.usable_minutes, 1), end, end, ["EVA model (team assumptions)"], "model estimate")
    elif need_min > 0.8 * eva.usable_minutes:
        add("R5_EVA_BUDGET", "caution", "Close to the EVA time budget",
            f"Modelled time {need_min:.0f} min uses more than 80% of the usable {eva.usable_minutes:.0f} min.",
            "required time > 80% of usable budget", round(need_min, 1), "min", round(eva.usable_minutes, 1), end, end,
            ["EVA model (team assumptions)"], "model estimate")
    # R6 snapped points
    for s in stops:
        if s["snapped_m"] > 15:
            i = min(int(np.searchsorted(cum_d, s["at_distance_km"] * 1000)), end)
            add("R6_POINT_MOVED", "info", f"'{s['name']}' moved {s['snapped_m']:.0f} m",
                "The requested point is on terrain outside the EVA limits; the nearest walkable cell was used.",
                "requested cell not walkable under EVA limits", s["snapped_m"], "m", None, i, i,
                ["EVA limits applied to slope/roughness"], "model-derived")
    order = {"warning": 0, "caution": 1, "info": 2}
    W.sort(key=lambda w: (order[w["severity"]], w["at_distance_km"]))
    for i, w in enumerate(W):
        w["id"] = f"w{i+1:02d}"
    return W
