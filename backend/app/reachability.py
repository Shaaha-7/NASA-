"""Walking range ("how far can I walk and still get back?") from a start point such as a habitat.

Two Dijkstra searches on the same terrain-cost model as the route planner ("fastest" profile):
* outbound: modelled walking time from the start to every cell;
* inbound: modelled walking time from every cell back to the start. Uphill and downhill
  differ, so the two are not the same.
A cell is in range when outbound + inbound (round trip) fits the usable EVA time
(EVA hours minus reserve). With round_trip=False only the outbound time counts.

Output is map-ready GeoJSON for the frontend: nested range bands at 25/50/75/100 % of the
usable time, plus the curated science stops that fall inside the range with their times.
Everything is a MODEL ESTIMATE under team assumptions, never a statement that ground is safe.
"""
from __future__ import annotations

import heapq
import math
import time

import numpy as np

from .eva import EvaParams, TOBLER_K, TOBLER_OPT
from .geo import MARS_RADIUS_M, haversine_m
from .region_store import Region
from .routing import HAVE_NUMBA, build_masks, njit, snap

BAND_FRACTIONS = (0.25, 0.5, 0.75, 1.0)


def _dijkstra_impl(elev, passable, mult, H, W, dx_rows, dy, start, v_flat, max_grade, inbound, limit_s):
    """Least walking time between `start` and every cell (seconds; inf if unreachable).
    inbound=False: time FROM start TO the cell. inbound=True: time FROM the cell TO start.
    Search stops expanding beyond limit_s (nothing further can be in range)."""
    n = H * W
    INF = 1e300
    t = np.full(n, INF)
    done = np.zeros(n, dtype=np.bool_)
    norm = math.exp(-TOBLER_K * TOBLER_OPT)
    t[start] = 0.0
    heap = [(0.0, np.int64(start))]
    drs = (-1, -1, -1, 0, 0, 1, 1, 1)
    dcs = (-1, 0, 1, -1, 1, -1, 0, 1)
    while len(heap) > 0:
        tc, cur = heapq.heappop(heap)
        if done[cur]:
            continue
        done[cur] = True
        if tc > limit_s:
            break
        r = cur // W
        c = cur % W
        for k in range(8):
            nr = r + drs[k]
            nc = c + dcs[k]
            if nr < 0 or nr >= H or nc < 0 or nc >= W:
                continue
            nb = nr * W + nc
            if done[nb] or not passable[nb]:
                continue
            dxm = 0.5 * (dx_rows[r] + dx_rows[nr]) * dcs[k]
            dym = dy * drs[k]
            d = math.sqrt(dxm * dxm + dym * dym)
            # walking direction: outbound cur -> nb ; inbound nb -> cur
            dz = (elev[nb] - elev[cur]) if not inbound else (elev[cur] - elev[nb])
            grade = dz / d
            if abs(grade) > max_grade:
                continue
            v = v_flat * math.exp(-TOBLER_K * abs(grade + TOBLER_OPT)) / norm
            nt = tc + d / v * 0.5 * (mult[cur] + mult[nb])
            if nt < t[nb]:
                t[nb] = nt
                heapq.heappush(heap, (nt, np.int64(nb)))
    return t


_dijkstra = njit(cache=True)(_dijkstra_impl) if HAVE_NUMBA else _dijkstra_impl


def _bands_geojson(region: Region, band: np.ndarray, usable_s: float, min_cells: int = 12) -> list[dict]:
    """Polygons for each cumulative band (time <= fraction x usable). Small specks are removed."""
    from rasterio import features
    g = region.grid
    feats = []
    for i, frac in enumerate(BAND_FRACTIONS, start=1):
        mask = ((band > 0) & (band <= i)).astype("uint8")
        if not mask.any():
            continue
        mask = features.sieve(mask, size=min_cells, connectivity=8)
        cell_area_km2 = g.dy_m * float(region.dx_rows.mean()) / 1e6
        polys = []
        for geom, val in features.shapes(mask, mask=mask.astype(bool), transform=g.affine(), connectivity=8):
            if val != 1:
                continue
            polys.append([[[round(x, 6), round(y, 6)] for x, y in ring] for ring in geom["coordinates"]])
        if not polys:
            continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "MultiPolygon", "coordinates": polys},
            "properties": {"band": i, "fraction_of_usable_time": frac,
                           "round_trip_min_max": round(frac * usable_s / 60, 1),
                           "area_km2": round(float(mask.sum()) * cell_area_km2, 3),
                           "measured_or_derived": "model estimate (team EVA assumptions)"},
        })
    return feats


def compute_reachability(region: Region, lon: float, lat: float, eva: EvaParams,
                         science_sites: list[dict] | None = None) -> dict:
    t0 = time.perf_counter()
    g = region.grid
    passable, mult = build_masks(region, eva)
    start, snapped_m = snap(region, passable, lon, lat)
    usable_s = eva.usable_minutes * 60.0
    args = (region.elev_flat, passable, mult, g.height, g.width, region.dx_rows, g.dy_m, int(start),
            eva.flat_speed_ms, eva.max_grade)
    t_out = _dijkstra(*args, False, usable_s)
    if eva.round_trip:
        t_back = _dijkstra(*args, True, usable_s)
        total = t_out + t_back
    else:
        t_back = None
        total = t_out
    total = np.where(np.isfinite(total) & (total < 1e299), total, np.inf)

    # band index per cell: 1..4 = within 25/50/75/100 % of usable time, 0 = out of range
    band = np.zeros(total.size, dtype="uint8")
    for i, frac in reversed(list(enumerate(BAND_FRACTIONS, start=1))):
        band[total <= frac * usable_s] = i
    band2d = band.reshape(g.height, g.width)
    inrange = band > 0

    s_lon, s_lat = g.center_of(int(start) // g.width, int(start) % g.width)
    far = None
    if inrange.any():
        idx = np.flatnonzero(inrange)
        rr, cc = idx // g.width, idx % g.width
        lons = g.west + (cc + 0.5) * g.dlon
        lats = g.north - (rr + 0.5) * g.dlat
        # straight-line distance on the sphere for every in-range cell; report the farthest
        p1, p2 = math.radians(s_lat), np.radians(lats)
        a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lons - s_lon) / 2) ** 2
        dist = 2 * MARS_RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(a)))
        k = int(np.argmax(dist))
        far = {"lon": round(float(lons[k]), 6), "lat": round(float(lats[k]), 6),
               "straight_line_km": round(float(dist[k]) / 1000, 3),
               "round_trip_min": round(float(total[idx[k]]) / 60, 1)}

    sites_in_range = []
    for f in science_sites or []:
        p = f.get("properties", {})
        lo, la = f["geometry"]["coordinates"][:2]
        if not g.contains(lo, la):
            continue
        r, c = g.cell_of(lo, la)
        i = r * g.width + c
        if not passable[i]:
            # stops sit on outcrops: use the nearest walkable cell, like the route planner
            try:
                i, _ = snap(region, passable, lo, la)
            except Exception:
                continue
        tt = float(total[i])
        entry = {"id": p.get("id"), "name": p.get("name"), "goal_id": p.get("goal_id"),
                 "lon": lo, "lat": la, "straight_line_km": round(haversine_m(s_lon, s_lat, lo, la) / 1000, 3),
                 "in_range": bool(np.isfinite(tt) and tt <= usable_s)}
        if np.isfinite(tt):
            entry["round_trip_min" if eva.round_trip else "outbound_min"] = round(tt / 60, 1)
            entry["outbound_min"] = round(float(t_out[i]) / 60, 1)
        sites_in_range.append(entry)
    sites_in_range.sort(key=lambda e: (not e["in_range"], e.get("round_trip_min", e.get("outbound_min", 1e9))))

    cell_km2 = g.dy_m * float(region.dx_rows.mean()) / 1e6
    return {
        "region_id": region.region_id,
        "is_test_fixture": region.is_test_fixture,
        "start": {"requested": [lon, lat], "snapped": [round(s_lon, 6), round(s_lat, 6)],
                  "snapped_m": round(float(snapped_m), 1)},
        "mode": "round trip (out and back)" if eva.round_trip else "outbound only",
        "usable_min": round(eva.usable_minutes, 1),
        "reachable_area_km2": round(float(inrange.sum()) * cell_km2, 3),
        "farthest_point": far,
        "bands": {"type": "FeatureCollection", "features": _bands_geojson(region, band2d, usable_s)},
        "science_sites": sites_in_range,
        "eva_params": eva.as_dict(),
        "assumptions": ["Walking time uses the route planner's 'fastest' model (Tobler speed vs signed grade, "
                        "roughness and geologic-unit multipliers, slope and roughness limits)."] + eva.assumptions(),
        "limitations": ["Model estimate under team assumptions, not a certified safe zone; ground outside the "
                        "bands is not necessarily unsafe and ground inside is not necessarily safe.",
                        f"Terrain resolved at {g.mean_res_m:.0f} m; smaller obstacles are not seen.",
                        "No live conditions (dust, lighting, radiation) are in the walking time."],
        "grid_resolution_m": round(g.mean_res_m, 1),
        "compute_ms": round((time.perf_counter() - t0) * 1000, 1),
        "engine": "Dijkstra (numba)" if HAVE_NUMBA else "Dijkstra (pure Python)",
    }
