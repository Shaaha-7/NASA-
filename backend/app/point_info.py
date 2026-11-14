"""'What's here?': everything MarsPath knows about one point, in one response.

Terrain values come from the processed numerical DEM grid (never from images). Walkability uses
the same EVA limits as the route planner and says WHY a cell is excluded. Nearby context (science
sites, rover stops, hazard zones) uses straight-line distances on the Mars sphere. With a `from`
point the round-trip walking time is computed with the route planner itself.
"""
from __future__ import annotations

import numpy as np

from .eva import EvaParams
from .geo import haversine_m
from .region_store import Region
from .routing import RouteError, compute_route

NEIGHBOURHOOD_M = 50.0


def _nearest(features: list[dict], lon: float, lat: float, label_key: str = "name"):
    best = None
    for f in features:
        lo, la = f["geometry"]["coordinates"][:2]
        d = haversine_m(lon, lat, lo, la)
        if best is None or d < best[0]:
            best = (d, f)
    if best is None:
        return None
    d, f = best
    p = f.get("properties", {})
    return {"id": p.get("id"), "name": p.get(label_key) or p.get("name"), "distance_m": round(d, 1),
            "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1], "properties": p}


def point_info(region: Region, lon: float, lat: float, eva: EvaParams,
               from_lonlat: tuple[float, float] | None = None) -> dict:
    g = region.grid
    s = region.sample(lon, lat)
    if not s.get("inside"):
        return {"inside": False, "message": f"Point is outside region '{region.region_id}'."}
    r, c = s["cell"]

    # walkability with reasons (same rules as routing.build_masks)
    reasons = []
    if s["elevation_m"] is None:
        reasons.append("no elevation data")
    if s["slope_deg"] is not None and s["slope_deg"] > eva.max_slope_deg:
        reasons.append(f"slope {s['slope_deg']:.1f} deg > EVA limit {eva.max_slope_deg:g} deg")
    if s["roughness_m"] is not None and s["roughness_m"] > eva.roughness_max_m:
        reasons.append(f"roughness {s['roughness_m']:.2f} m > EVA limit {eva.roughness_max_m:g} m")
    units = {u["name"]: u for u in region.manifest.get("units", [])}
    unit = units.get(s.get("geologic_unit")) if s.get("geologic_unit") else None

    # neighbourhood: steepest slope and highest roughness within NEIGHBOURHOOD_M
    rad_r = max(1, int(round(NEIGHBOURHOOD_M / g.dy_m)))
    rad_c = max(1, int(round(NEIGHBOURHOOD_M / float(region.dx_rows[r]))))
    win = (slice(max(0, r - rad_r), r + rad_r + 1), slice(max(0, c - rad_c), c + rad_c + 1))
    sl, rg, el = region.slope[win], region.rough[win], region.elev[win]
    neigh = {"radius_m": NEIGHBOURHOOD_M,
             "max_slope_deg": round(float(np.nanmax(sl)), 1) if np.isfinite(sl).any() else None,
             "max_roughness_m": round(float(np.nanmax(rg)), 2) if np.isfinite(rg).any() else None,
             "relief_m": round(float(np.nanmax(el) - np.nanmin(el)), 1) if np.isfinite(el).any() else None}

    sites = region.read_geojson("science_sites.geojson").get("features", [])
    wps = region.read_geojson("rover_waypoints.geojson").get("features", [])
    hz = region.read_geojson("hazards.geojson").get("features", [])
    site = _nearest(sites, lon, lat)
    wp = _nearest(wps, lon, lat)
    hazard = _nearest(hz, lon, lat, label_key="type")

    out = {
        "inside": True, "region_id": region.region_id, "is_test_fixture": region.is_test_fixture,
        "lon": lon, "lat": lat,
        "terrain": {"elevation_m": s["elevation_m"], "slope_deg": s["slope_deg"], "roughness_m": s["roughness_m"],
                    "dem_source": s.get("dem_source"),
                    "data_basis": "processed numerical DEM grid "
                                  f"({g.mean_res_m:.0f} m cells; roughness from the finest DEM available)"},
        "neighbourhood": neigh,
        "geology": ({"unit": unit["name"], "walking_time_multiplier": unit["multiplier"], "flag": unit.get("flag"),
                     "reason": unit.get("reason"),
                     "source": region.manifest["sources"].get("geo_units", {}).get("label")} if unit else None),
        "walkable": not reasons, "not_walkable_because": reasons,
        "eva_limits": {"max_slope_deg": eva.max_slope_deg, "roughness_max_m": eva.roughness_max_m},
        "nearest_science_site": ({k: site[k] for k in ("id", "name", "distance_m", "lon", "lat")} |
                                 {"goal_id": site["properties"].get("goal_id"),
                                  "source_url": site["properties"].get("source_url")}) if site else None,
        "nearest_rover_stop": ({"sol": wp["properties"].get("sol"), "distance_m": wp["distance_m"],
                                "lon": wp["lon"], "lat": wp["lat"],
                                "ground_view": f"/api/v1/ground-view?region_id={region.region_id}"
                                               f"&lon={wp['lon']:.6f}&lat={wp['lat']:.6f}"} if wp else None),
        "nearest_hazard_zone": ({"type": hazard["properties"].get("type"), "severity": hazard["properties"].get("severity"),
                                 "rule": hazard["properties"].get("rule"), "distance_m": hazard["distance_m"],
                                 "note": "distance to the zone's centre point; model-derived"} if hazard else None),
    }
    if from_lonlat:
        try:
            rt = compute_route(region, [from_lonlat, (lon, lat)], eva, "fastest")
            out["walk_from_start"] = {"from": list(from_lonlat), "distance_km": rt["distance_km"],
                                      "outbound_min": rt["duration_min"], "return_min": rt["return_duration_min"],
                                      "within_eva_budget": rt["eva"]["within_budget"],
                                      "usable_min": rt["eva"]["usable_min"], "estimate": True}
        except RouteError as e:
            out["walk_from_start"] = {"from": list(from_lonlat), "error": e.code, "message": str(e)}
    return out
