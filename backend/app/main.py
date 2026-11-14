"""MarsPath API (FastAPI). Run:  uvicorn app.main:app --app-dir backend --port 8000

Every scientific output carries provenance (mission, instrument/dataset, processing, limitations).
Missing values are null, never 0. The same code serves online and offline: it reads only the
processed local package and calls the network only for optional live extras.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import assistant, config, netutil, offline, spaceweather
from .eva import EvaParams
from .geo import COORDINATE_CONVENTION, validate_lonlat
from .region_store import available_region_ids, get_region
from .routing import HAVE_NUMBA, PROFILES, RouteError, compute_route, optimise_stop_order
from .schemas import AskRequest, CompareRequest, MissionRequest, RouteRequest

VERSION = "1.0.0"
app = FastAPI(title="MarsPath API", version=VERSION,
              description="Terrain-aware Marswalk planner for NASA Space Apps 2026 - Interplanetary Survival Guide: Martian Map")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
API = "/api/v1"


def _region_or_404(region_id: str):
    r = get_region(region_id)
    if r is None:
        raise HTTPException(404, detail={"code": "unsupported_region",
                                         "message": f"Region '{region_id}' is not prepared on this machine.",
                                         "available": available_region_ids()})
    return r


@app.exception_handler(RouteError)
async def route_error_handler(_, exc: RouteError):
    status = 422 if exc.code in ("outside_region", "bad_profile", "bad_request") else 409
    return JSONResponse(status_code=status, content={"detail": {"code": exc.code, "message": str(exc), **exc.detail}})


@app.exception_handler(ValueError)
async def value_error_handler(_, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": {"code": "invalid_input", "message": str(exc)}})

# ------------------------------------------------------------------ status


@app.get(f"{API}/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get(f"{API}/status")
def status():
    regions = available_region_ids()
    return {"version": VERSION, "online": netutil.is_online(), "force_offline": config.FORCE_OFFLINE,
            "regions_ready": regions, "routing_engine": "A* (numba)" if HAVE_NUMBA else "A* (pure Python)",
            "assistant_index": assistant.INDEX.exists(), "llm_configured": bool(config.ANTHROPIC_API_KEY),
            "nasa_api_key": "custom" if config.NASA_API_KEY != "DEMO_KEY" else "DEMO_KEY (rate limited)",
            "coordinate_convention": COORDINATE_CONVENTION,
            "server_time_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}

# ------------------------------------------------------------------ regions & layers


@app.get(f"{API}/regions")
def regions():
    out = []
    for rid in available_region_ids():
        r = get_region(rid)
        m = r.manifest
        out.append({"region_id": rid, "name": m["name"], "is_test_fixture": r.is_test_fixture, "bbox": m["bbox"],
                    "center": m["center"], "layers": [l["id"] for l in m["layers"]],
                    "resolution_m": round(r.grid.mean_res_m, 1), "data_date": m.get("data_date"),
                    "processed_at": m.get("processed_at"), "elevation_stats": m.get("elevation_stats"),
                    "offline_package": "ready", "science_goals": m.get("science_goals", [])})
    return {"regions": out, "coordinate_convention": COORDINATE_CONVENTION}


@app.get(f"{API}/layers")
def layers(region_id: str):
    r = _region_or_404(region_id)
    ls = []
    for l in r.manifest["layers"]:
        l = dict(l)
        l["url"] = f"{API}/regions/{region_id}/{l['url']}"
        l["available"] = True
        ls.append(l)
    for lid, (name, ext, label, mission, inst, res) in config.TREK_LAYERS.items():
        ls.append({"id": f"trek_{lid}", "kind": "tiles", "name": label, "url": f"{API}/tiles/{lid}/{{z}}/{{y}}/{{x}}",
                   "mission": mission, "instrument": inst, "resolution": res, "source": "NASA JPL Mars Trek WMTS",
                   "source_url": config.TREK_SOURCE_URL, "measured_or_derived": "measured (global mosaic)",
                   "limitations": "Global context only; far too coarse for walking-scale decisions. Cached tiles only when offline.",
                   "default_on": True, "opacity": 1.0, "available": True})
    return {"region_id": region_id, "layers": ls, "notes": r.manifest.get("notes", []),
            "sources": r.manifest.get("sources", {})}


@app.get(API + "/regions/{region_id}/layers/{name}")
def layer_image(region_id: str, name: str):
    r = _region_or_404(region_id)
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "bad name")
    p = r.folder / "layers" / name
    if not p.exists():
        raise HTTPException(404, detail={"code": "not_available", "message": "Layer not available for this region"})
    return FileResponse(p, headers={"Cache-Control": "public, max-age=3600"})


@app.get(API + "/tiles/{layer}/{z}/{y}/{x}")
def tiles(layer: str, z: int, y: int, x: int):
    if layer not in config.TREK_LAYERS or not (0 <= z <= 12):
        raise HTTPException(404)
    p = offline.fetch_tile(layer, z, y, x)
    if p is None:
        return Response(status_code=404, headers={"X-MarsPath": "tile-not-cached-offline"})
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})


@app.get(f"{API}/terrain/sample")
def terrain_sample(region_id: str, lon: float, lat: float):
    validate_lonlat(lon, lat)
    r = _region_or_404(region_id)
    if not r.grid.contains(lon, lat):
        raise HTTPException(422, detail={"code": "outside_region", "message": "Point outside the region"})
    s = r.sample(lon, lat)
    s["source"] = r.manifest["sources"].get("dem_primary" if s["dem_source"] == "primary" else "dem_fallback", {}).get("label")
    s["is_test_fixture"] = r.is_test_fixture
    return s

# ------------------------------------------------------------------ pins


@app.get(f"{API}/science-sites")
def science_sites(region_id: str, include_rover: bool = True):
    r = _region_or_404(region_id)
    curated = r.read_geojson("science_sites.geojson")
    feats = list(curated.get("features", []))
    if include_rover:
        feats += r.read_geojson("rover_waypoints.geojson").get("features", [])
    return {"type": "FeatureCollection", "features": feats, "traverse": r.read_geojson("rover_traverse.geojson"),
            "science_goals": r.manifest.get("science_goals", []), "is_test_fixture": r.is_test_fixture,
            "note": "Rover waypoints are measured positions from NASA/JPL MMGIS. Curated sites come from "
                    "config/science_sites/<region>.geojson and must each cite a source."}


@app.get(f"{API}/hazards")
def hazards(region_id: str, max_slope_deg: float | None = None, roughness_max_m: float | None = None):
    r = _region_or_404(region_id)
    if max_slope_deg is None and roughness_max_m is None:
        fc = r.read_geojson("hazards.geojson")
    else:
        from .processing import detect_hazards
        eva = EvaParams.defaults().merged({"max_slope_deg": max_slope_deg, "roughness_max_m": roughness_max_m})
        fc = {"type": "FeatureCollection", "features": detect_hazards(r.slope, r.rough, r.grid, eva.max_slope_deg,
                                                                        eva.roughness_max_m)}
    return {**fc, "is_test_fixture": r.is_test_fixture,
            "note": "Rule-based, model-derived terrain cautions from numerical elevation. Not observed obstacles "
                    "and never a statement that other ground is safe."}


@app.get(f"{API}/validation")
def validation(region_id: str):
    """Planner vs Perseverance's real drives (built by backend/scripts/validate_against_rover.py)."""
    r = _region_or_404(region_id)
    f = r.folder / "validation.json"
    if not f.exists():
        raise HTTPException(404, detail={"code": "not_available",
                                         "message": "No rover benchmark for this region yet. Run "
                                                    "backend/scripts/validate_against_rover.py " + region_id})
    return json.loads(f.read_text(encoding="utf-8"))

# ------------------------------------------------------------------ routes


@app.get(f"{API}/eva/defaults")
def eva_defaults():
    return {"params": EvaParams.defaults().as_dict(), "descriptions": config.eva_defaults(),
            "profiles": {k: v["label"] for k, v in PROFILES.items()}}


def _route_inputs(req):
    r = _region_or_404(req.region_id)
    pts = [req.start] + list(req.stops) + [req.destination]
    for p in pts:
        validate_lonlat(p.lon, p.lat)
    eva = EvaParams.defaults().merged(req.eva.model_dump(exclude_none=True))
    names = [p.name for p in pts]
    return r, [(p.lon, p.lat) for p in pts], eva, names


def _attach_space_weather(route: dict, eva: EvaParams):
    try:
        sw = spaceweather.summary(eva_hours=eva.eva_hours, allow_fetch=False)
    except Exception:
        return route
    adv = sw.get("advisory", {})
    route["space_weather"] = {"status": sw["status"], "advisory": adv, "fetched_at": sw.get("fetched_at"),
                              "eva_reference_dose_mSv": sw["eva_reference_dose_mSv"]}
    if adv.get("level") == "caution":
        route["warnings"].insert(0, {"id": "w00", "rule_id": "R7_SPACE_WEATHER", "severity": "caution",
                                     "title": "Recent solar particle activity", "explanation": adv["text"],
                                     "rule": "SEP event in last 7 days of cached DONKI window", "value": None,
                                     "unit": None, "threshold": None, "location": route["stops"][0]["snapped"],
                                     "at_distance_km": 0.0, "length_m": 0, "data_basis": ["NASA CCMC DONKI"],
                                     "measured_or_derived": "catalogue advisory (near-Earth observations)"})
    return route


@app.post(f"{API}/routes/calculate")
def routes_calculate(req: RouteRequest):
    r, pts, eva, names = _route_inputs(req)
    opt = None
    if req.optimise_stop_order and len(pts) > 3:
        opt = optimise_stop_order(r, pts, eva, req.profile)
        order = [0] + [k + 1 for k in opt["order"]] + [len(pts) - 1]
        pts, names = [pts[i] for i in order], [names[i] for i in order]
    route = compute_route(r, pts, eva, req.profile, names)
    route["stop_order"] = opt or {"order": list(range(len(pts) - 2)), "changed": False}
    route["offline"] = not netutil.is_online()
    return _attach_space_weather(route, eva)


@app.post(f"{API}/routes/compare")
def routes_compare(req: CompareRequest):
    r, pts, eva, names = _route_inputs(req)
    out, errors = [], []
    for prof in dict.fromkeys(req.profiles):
        try:
            out.append(compute_route(r, pts, eva, prof, names))
        except RouteError as e:
            errors.append({"profile": prof, "code": e.code, "message": str(e)})
    if not out:
        raise HTTPException(409, detail={"code": "no_route", "errors": errors})
    keys = ["distance_km", "duration_min", "return_duration_min", "max_slope_deg", "mean_slope_deg", "ascent_m",
            "descent_m", "max_roughness_m"]
    table = [{"profile": x["profile"], **{k: x[k] for k in keys}, "within_budget": x["eva"]["within_budget"],
              "warnings": len(x["warnings"])} for x in out]
    best = {k: min(table, key=lambda t: (t[k] if t[k] is not None else 1e9))["profile"] for k in
            ("distance_km", "duration_min", "max_slope_deg")}
    return {"region_id": req.region_id, "routes": out, "comparison": table, "best": best, "errors": errors}

# ------------------------------------------------------------------ missions


def _mission_path(mid: str):
    if not mid.replace("-", "").isalnum():
        raise HTTPException(400, "bad id")
    return config.MISSIONS_DIR / f"{mid}.json"


@app.post(f"{API}/missions")
def missions_create(req: MissionRequest):
    _region_or_404(req.region_id)
    mid = f"mission-{uuid.uuid4().hex[:8]}"
    doc = {"mission_id": mid, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           **req.model_dump()}
    _mission_path(mid).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return {"mission_id": mid, "created_at": doc["created_at"],
            "export": {f: f"{API}/missions/{mid}/export?format={f}" for f in ("geojson", "csv", "json")}}


@app.get(f"{API}/missions")
def missions_list():
    items = []
    for p in sorted(config.MISSIONS_DIR.glob("mission-*.json"), key=lambda p: -p.stat().st_mtime):
        d = json.loads(p.read_text(encoding="utf-8"))
        items.append({"mission_id": d["mission_id"], "name": d["name"], "region_id": d["region_id"],
                      "created_at": d["created_at"], "distance_km": d["route"].get("distance_km")})
    return {"missions": items}


@app.get(API + "/missions/{mid}")
def missions_get(mid: str):
    p = _mission_path(mid)
    if not p.exists():
        raise HTTPException(404, detail={"code": "not_found"})
    return json.loads(p.read_text(encoding="utf-8"))


@app.get(API + "/missions/{mid}/export")
def missions_export(mid: str, format: str = Query("geojson", pattern="^(geojson|csv|json)$")):
    d = missions_get(mid)
    route = d["route"]
    fname = f"{mid}.{format}"
    if format == "json":
        body, mt = json.dumps(d, indent=2), "application/json"
    elif format == "geojson":
        feats = [{"type": "Feature", "geometry": route["geometry"],
                  "properties": {k: route.get(k) for k in ("route_id", "profile", "distance_km", "duration_min",
                                                          "max_slope_deg", "ascent_m", "descent_m")} | {"mission": d["name"]}}]
        for s in route.get("stops", []):
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": s["snapped"]},
                          "properties": {"kind": "stop", **s}})
        for w in route.get("warnings", []):
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": w["location"]},
                          "properties": {"kind": "warning", **{k: w[k] for k in ("rule_id", "severity", "title", "rule")}}})
        body, mt = json.dumps({"type": "FeatureCollection", "features": feats}, indent=1), "application/geo+json"
    else:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["# MarsPath mission", d["name"], "region", d["region_id"], "route", route.get("route_id")])
        w.writerow(["# coordinates: lon east-positive, planetocentric lat, Mars 2000 sphere; values are model estimates"])
        w.writerow(["distance_km", "elevation_m", "grade_deg", "lon", "lat"])
        for p in route.get("elevation_profile", []):
            w.writerow([p["distance_km"], p["elevation_m"], p["grade_deg"], p["lon"], p["lat"]])
        body, mt = buf.getvalue(), "text/csv"
    return Response(body, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{fname}"'})

# ------------------------------------------------------------------ space weather


@app.get(f"{API}/space-weather")
def space_weather(eva_hours: float = 4.0, refresh: bool = False):
    if refresh and netutil.is_online():
        try:
            spaceweather.refresh(30)
        except Exception as e:
            return {**spaceweather.summary(eva_hours=eva_hours, allow_fetch=False), "refresh_error": spaceweather._clean(e)[:200]}
    return spaceweather.summary(eva_hours=eva_hours)

# ------------------------------------------------------------------ offline


@app.get(f"{API}/offline/package")
def offline_package(region_id: str, download: bool = False):
    _region_or_404(region_id)
    if download:
        p = offline.build_zip(region_id)
        return FileResponse(p, filename=p.name, media_type="application/zip")
    return offline.manifest(region_id)


@app.post(f"{API}/offline/prefetch")
def offline_prefetch(region_id: str, zmax: int = 9):
    _region_or_404(region_id)
    if not netutil.is_online(force_check=True):
        raise HTTPException(503, detail={"code": "offline", "message": "Prefetch needs a network connection."})
    return offline.prefetch(region_id, zmax=min(zmax, 11))

# ------------------------------------------------------------------ assistant


@app.post(f"{API}/assistant/ask")
def assistant_ask(req: AskRequest):
    region_name = None
    if req.region_id:
        r = get_region(req.region_id)
        region_name = r.manifest["name"] if r else None
    res = assistant.ask(req.question, region_name, req.lon, req.lat)
    res["offline"] = not netutil.is_online()
    return res


@app.post(f"{API}/assistant/reindex")
def assistant_reindex():
    return assistant.build_index()

# ------------------------------------------------------------------ frontend


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


app.mount("/app", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="app")
