"""Turn-by-turn EVA directions from a computed route.

The route is resampled every SAMPLE_M metres; each sample gets a compass heading. Runs with the
same 8-point heading become one step; steps shorter than MIN_STEP_M are merged into a neighbour.
Steps also break at every stop. Each step reports distance, modelled time, climb/descent,
steepest grade, the geologic unit walked most, any warnings on it, and curated science sites
passed within LANDMARK_M (with the side they are on). Everything comes from the same arrays the
route metrics use, so directions and metrics always agree.
"""
from __future__ import annotations

import math

import numpy as np

SAMPLE_M = 40.0
MIN_STEP_M = 90.0
LANDMARK_M = 150.0
COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def _compass(bearing: float) -> str:
    return COMPASS[int(((bearing % 360) + 22.5) // 45) % 8]


def _turn(prev: float, new: float) -> str:
    d = (new - prev + 540) % 360 - 180  # -180..180, positive = clockwise = right
    a = abs(d)
    if a < 20:
        return "Continue"
    side = "right" if d > 0 else "left"
    if a < 60:
        return f"Bear {side}"
    if a < 135:
        return f"Turn {side}"
    return f"Turn sharply {side}"


def build(lonlat: list[tuple[float, float]], cum_d: np.ndarray, cum_t: np.ndarray, z: np.ndarray,
          grade_deg: np.ndarray, unit_names: list[str | None], break_at: list[int], stop_names: list[str],
          sites: list[dict], warnings: list[dict], mars_r: float) -> list[dict]:
    n = len(lonlat)
    if n < 2:
        return []
    lat0 = math.radians(sum(p[1] for p in lonlat) / n)
    xy = np.array([(math.radians(lo) * mars_r * math.cos(lat0), math.radians(la) * mars_r) for lo, la in lonlat])

    # cut points: every SAMPLE_M along the path, plus every stop
    cuts = sorted(set([0, n - 1] + [int(i) for i in break_at if 0 < i < n - 1] +
                      [int(np.searchsorted(cum_d, s)) for s in np.arange(SAMPLE_M, cum_d[-1], SAMPLE_M)]))
    cuts = [c for c in cuts if c < n]
    pieces = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b <= a:
            continue
        dx, dy = xy[b] - xy[a]
        brg = (math.degrees(math.atan2(dx, dy)) + 360) % 360
        pieces.append([a, b, brg])

    # group consecutive pieces with the same compass heading, never across a stop
    stops = set(int(i) for i in break_at)
    steps = []
    for a, b, brg in pieces:
        if steps and _compass(steps[-1][2]) == _compass(brg) and a not in stops:
            steps[-1][1] = b
        else:
            steps.append([a, b, brg])
    # merge short steps into the previous one (not across stops)
    merged = []
    for s in steps:
        if merged and cum_d[s[1]] - cum_d[s[0]] < MIN_STEP_M and s[0] not in stops:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    for s in merged:  # recompute heading over the whole step
        dx, dy = xy[s[1]] - xy[s[0]]
        s[2] = (math.degrees(math.atan2(dx, dy)) + 360) % 360

    out = []
    prev_brg = None
    stop_iter = {int(i): nm for i, nm in zip(break_at, stop_names[1:])}
    for k, (a, b, brg) in enumerate(merged):
        dist = float(cum_d[b] - cum_d[a])
        dt_min = float(cum_t[b] - cum_t[a]) / 60
        dz = float(z[b] - z[a])
        seg_dz = np.diff(z[a:b + 1])
        climb, desc = float(seg_dz[seg_dz > 0].sum()), float(-seg_dz[seg_dz < 0].sum())
        gmax = float(np.max(grade_deg[a:b])) if b > a else 0.0
        units = [u for u in unit_names[a:b + 1] if u]
        unit = max(set(units), key=units.count) if units else None
        # landmarks passed
        passed = []
        seg = xy[a:b + 1]
        hx, hy = math.sin(math.radians(brg)), math.cos(math.radians(brg))
        for f in sites:
            p = f.get("properties", {})
            lo, la = f["geometry"]["coordinates"][:2]
            sx, sy = math.radians(lo) * mars_r * math.cos(lat0), math.radians(la) * mars_r
            dd = np.hypot(seg[:, 0] - sx, seg[:, 1] - sy)
            j = int(np.argmin(dd))
            if j == 0 and dd[j] < 15:
                continue  # the step starts here (a stop just reached); not a landmark of this step
            if dd[j] <= LANDMARK_M:
                cross = hx * (sy - seg[j, 1]) - hy * (sx - seg[j, 0])
                side = "ahead" if dd[j] < 15 else ("on your left" if cross > 0 else "on your right")
                passed.append({"id": p.get("id"), "name": p.get("name"), "distance_m": round(float(dd[j])),
                               "side": side})
        step_warn = [w["id"] for w in warnings
                     if w.get("at_distance_km") is not None and cum_d[a] <= w["at_distance_km"] * 1000 <= cum_d[b]]
        verb = "Head" if prev_brg is None else _turn(prev_brg, brg)
        heading = _compass(brg)
        slope_txt = (f"climbing {climb:.0f} m" if dz > 2 else f"descending {desc:.0f} m" if dz < -2
                     else "on level ground")
        lead = f"Head {heading}" if verb == "Head" else f"{verb}, heading {heading},"
        text = f"{lead} for {dist:.0f} m (about {dt_min:.0f} min), {slope_txt}, steepest {gmax:.0f} deg"
        if unit:
            text += f", over the {unit}"
        if passed:
            text += "; " + "; ".join(f"{x['name']} {x['side']} ({x['distance_m']} m)" for x in passed)
        text += "."
        if b in stop_iter:
            text += f" Arrive at {stop_iter[b]}."
        out.append({"step": k + 1, "instruction": text, "verb": verb, "heading": heading,
                    "bearing_deg": round(brg, 0), "distance_m": round(dist, 0), "duration_min": round(dt_min, 1),
                    "climb_m": round(climb, 1), "descent_m": round(desc, 1), "max_grade_deg": round(gmax, 1),
                    "geologic_unit": unit, "landmarks": passed, "warning_ids": step_warn,
                    "start": [round(lonlat[a][0], 6), round(lonlat[a][1], 6)],
                    "end": [round(lonlat[b][0], 6), round(lonlat[b][1], 6)],
                    "at_distance_km": round(float(cum_d[a]) / 1000, 3), "arrive_stop": stop_iter.get(b)})
        prev_brg = brg
    return out
