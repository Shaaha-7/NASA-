"""Core tests. Run from the project root:  python -m pytest backend/tests -q
They use small in-memory grids and the synthetic region (built automatically if missing)."""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import assistant, config  # noqa: E402
from app.eva import EvaParams  # noqa: E402
from app.geo import Grid, haversine_m, MARS_RADIUS_M  # noqa: E402
from app.processing import roughness_m, slope_deg, detect_hazards  # noqa: E402


@pytest.fixture(scope="session")
def synthetic():
    if not (config.PROCESSED_DIR / "synthetic" / "manifest.json").exists():
        subprocess.run([sys.executable, str(ROOT / "backend/scripts/make_synthetic.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "backend/scripts/prepare_data.py"), "synthetic"], check=True)
    from app.region_store import get_region
    return get_region("synthetic")


# ---------------------------------------------------------------- geometry / units

def test_grid_metres():
    g = Grid.from_bbox(77.35, 18.38, 77.50, 18.50, 10)
    assert abs(g.dy_m - 10) < 0.01
    assert abs(g.dx_m_rows().mean() - 10) < 0.05
    lon, lat = g.center_of(*g.cell_of(77.4, 18.45))
    assert abs(lon - 77.4) < g.dlon and abs(lat - 18.45) < g.dlat


def test_haversine_one_degree_lat():
    assert abs(haversine_m(0, 0, 0, 1) - math.pi * MARS_RADIUS_M / 180) < 1


def test_slope_of_known_ramp():
    g = Grid.from_bbox(0, 0, 0.02, 0.02, 10)
    x = np.arange(g.width) * g.dx_m_rows()[0]
    z = np.tile(x * math.tan(math.radians(20)), (g.height, 1))
    s = slope_deg(z, g)
    assert abs(np.median(s) - 20) < 0.2


def test_nodata_stays_nan():
    g = Grid.from_bbox(0, 0, 0.01, 0.01, 10)
    z = np.zeros((g.height, g.width))
    z[5, 5] = np.nan
    assert np.isnan(slope_deg(z, g)[5, 5])
    assert np.isnan(roughness_m(z)[5, 5])


def test_hazard_detection_finds_steep_block():
    g = Grid.from_bbox(0, 0, 0.05, 0.05, 10)
    slope = np.zeros((g.height, g.width))
    slope[100:130, 100:130] = 40
    hz = detect_hazards(slope, np.zeros_like(slope), g, 25, 1.5)
    assert len(hz) == 1 and hz[0]["properties"]["type"] == "steep_slope"
    w, s, e, n = hz[0]["properties"]["bbox"]
    assert w < e and s < n

# ---------------------------------------------------------------- EVA model

def test_tobler_shape():
    e = EvaParams()
    assert abs(e.speed_ms(0) - e.flat_speed_ms) < 1e-9
    assert e.speed_ms(-0.05) > e.speed_ms(0) > e.speed_ms(0.2)
    assert e.speed_ms(0.3) < e.speed_ms(-0.3)  # uphill slower than the same downhill


def test_eva_validation():
    with pytest.raises(ValueError):
        EvaParams().merged({"max_slope_deg": 90})

# ---------------------------------------------------------------- routing

def test_route_detours_around_wall(synthetic):
    from app.routing import compute_route
    eva = EvaParams.defaults()
    r = compute_route(synthetic, [(120.005, 10.012), (120.01, 10.09)], eva, "fastest")
    assert r["distance_km"] > r["straight_line_km"] * 1.1  # must go around the scarp
    assert r["max_slope_deg"] <= eva.max_slope_deg + 1e-6
    assert r["geometry"]["type"] == "LineString" and len(r["geometry"]["coordinates"]) >= 2
    lon, lat = r["geometry"]["coordinates"][0]
    assert 120.0 <= lon <= 120.12 and 10.0 <= lat <= 10.1  # GeoJSON [lon, lat]
    assert r["is_test_fixture"] is True


def test_profiles_trade_off(synthetic):
    from app.routing import compute_route
    eva = EvaParams.defaults()
    pts = [(120.005, 10.012), (120.01, 10.09)]
    fast = compute_route(synthetic, pts, eva, "fastest")
    gentle = compute_route(synthetic, pts, eva, "gentlest")
    short = compute_route(synthetic, pts, eva, "shortest")
    assert short["distance_km"] <= fast["distance_km"] + 1e-6
    assert fast["duration_min"] <= short["duration_min"] + 1e-6
    assert gentle["max_slope_deg"] <= fast["max_slope_deg"] + 1e-6


def test_enclosed_point_is_explained(synthetic):
    from app.routing import compute_route, RouteError
    with pytest.raises(RouteError) as ei:
        compute_route(synthetic, [(120.005, 10.012), (120.0926, 10.028)], EvaParams.defaults())
    assert ei.value.code == "enclosed"


def test_outside_region(synthetic):
    from app.routing import compute_route, RouteError
    with pytest.raises(RouteError) as ei:
        compute_route(synthetic, [(10, 10), (120.01, 10.09)], EvaParams.defaults())
    assert ei.value.code == "outside_region"


def test_budget_warning(synthetic):
    from app.routing import compute_route
    eva = EvaParams.defaults().merged({"eva_hours": 1})
    r = compute_route(synthetic, [(120.005, 10.012), (120.01, 10.09)], eva)
    assert not r["eva"]["within_budget"]
    assert any(w["rule_id"] == "R5_EVA_BUDGET" and w["severity"] == "warning" for w in r["warnings"])

# ---------------------------------------------------------------- assistant

def test_assistant_retrieval(tmp_path):
    (tmp_path / "a.txt").write_text("Jezero crater hosts a delta. Carbonate minerals occur near the crater margin. " * 5)
    (tmp_path / "b.txt").write_text("Gale crater radiation was measured by the RAD instrument on Curiosity. " * 5)
    (tmp_path / "docs.json").write_text(json.dumps([
        {"file": "a.txt", "title": "A", "url": "http://a", "date": "2020", "licence": "pd"},
        {"file": "b.txt", "title": "B", "url": "http://b", "date": "2014", "licence": "pd"}]))
    out = tmp_path / "idx.json"
    assistant.build_index(tmp_path, out)
    import json as _j
    idx = _j.loads(out.read_text())
    hits = assistant.search("carbonate near the margin", idx=idx)
    assert hits and hits[0]["title"] == "A"

# ---------------------------------------------------------------- API

def test_api_end_to_end(synthetic, monkeypatch):
    monkeypatch.setattr(config, "FORCE_OFFLINE", True)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.get("/api/v1/regions").status_code == 200
    lay = c.get("/api/v1/layers?region_id=synthetic").json()["layers"]
    assert all("source" in l or "source_url" in l for l in lay)
    body = {"region_id": "synthetic", "start": {"lon": 120.005, "lat": 10.012},
            "destination": {"lon": 120.01, "lat": 10.09}, "profile": "gentlest"}
    r = c.post("/api/v1/routes/calculate", json=body)
    assert r.status_code == 200
    j = r.json()
    for k in ("route_id", "geometry", "distance_km", "max_slope_deg", "elevation_profile", "warnings",
              "data_sources", "assumptions", "limitations", "offline"):
        assert k in j
    assert j["offline"] is True
    assert c.post("/api/v1/routes/calculate", json={**body, "region_id": "nope"}).status_code == 404
    assert c.post("/api/v1/routes/calculate", json={**body, "start": {"lon": 0, "lat": 99}}).status_code == 422
    m = c.post("/api/v1/missions", json={"name": "t", "region_id": "synthetic", "route": j}).json()
    assert c.get(f"/api/v1/missions/{m['mission_id']}/export?format=geojson").status_code == 200
    (config.MISSIONS_DIR / f"{m['mission_id']}.json").unlink()


def test_stop_order_optimisation(synthetic):
    from app.routing import optimise_stop_order
    eva = EvaParams.defaults().merged({"eva_hours": 10})
    pts = [(120.005, 10.012), (120.07, 10.03), (120.02, 10.03), (120.06, 10.045), (120.03, 10.02), (120.012, 10.085)]
    o = optimise_stop_order(synthetic, pts, eva)
    assert sorted(o["order"]) == [0, 1, 2, 3]
    assert o["cost_optimised"] <= o["cost_as_given"]


def test_space_weather_errors_never_show_the_api_key():
    from app.spaceweather import _clean
    msg = ("Client error '404 Not Found' for url "
           "'https://api.nasa.gov/DONKI/FLR?startDate=2026-10-15&endDate=2026-11-14&api_key=SECRET123'")
    out = _clean(msg)
    assert "SECRET123" not in out and "api_key" not in out
    assert "api.nasa.gov/DONKI/FLR" in out


def test_curated_science_sites_are_sourced():
    """Every curated science stop must cite a source and sit inside its region's study box."""
    folder = config.CONFIG_DIR / "science_sites"
    for f in folder.glob("*.geojson"):
        if "TEMPLATE" in f.name:
            continue
        region = config.region_config(f.stem)
        if region and region.get("is_test_fixture"):
            continue  # synthetic test region: labelled TEST FIXTURE, no real source by design
        bbox = region["bbox"] if region else None
        for feat in json.loads(f.read_text(encoding="utf-8"))["features"]:
            p = feat["properties"]
            assert p.get("source") and str(p.get("source_url", "")).startswith("https://"), p.get("id")
            lon, lat = feat["geometry"]["coordinates"][:2]
            if bbox:
                assert bbox["west"] <= lon <= bbox["east"] and bbox["south"] <= lat <= bbox["north"], p.get("id")


def test_validation_endpoint_without_benchmark(synthetic):
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).get("/api/v1/validation", params={"region_id": "synthetic"})
    assert r.status_code in (200, 404)
    if r.status_code == 404:
        assert r.json()["detail"]["code"] == "not_available"


def test_reachability_bands_and_consistency(synthetic):
    """Walking range: nested bands grow with time, and the round trip to a point agrees with the router."""
    from app.reachability import compute_reachability
    from app.routing import compute_route
    eva = EvaParams.defaults().merged({"eva_hours": 6})
    start = (120.005, 10.012)
    r = compute_reachability(synthetic, *start, eva)
    areas = [f["properties"]["area_km2"] for f in r["bands"]["features"]]
    assert areas and areas == sorted(areas)
    assert r["reachable_area_km2"] > 0
    far = r["farthest_point"]
    route = compute_route(synthetic, [start, (far["lon"], far["lat"])], eva, "fastest")
    assert abs(route["eva"]["required_min"] - far["round_trip_min"]) <= 0.05 * far["round_trip_min"] + 1


def test_ground_view_offline_is_honest(synthetic, monkeypatch, tmp_path):
    """Offline with nothing cached: no images are invented, and the reason is reported."""
    from app import netutil, rover_images
    monkeypatch.setattr(rover_images, "CACHE_DIR", tmp_path / "raw_images")
    monkeypatch.setattr(netutil, "is_online", lambda: False)
    lon, lat = 120.03, 10.03
    gv = rover_images.ground_view(synthetic, lon, lat)
    if "rover_stop" in gv:
        assert gv["images"] == [] and gv["available"] is False
        assert all("offline" in s for s in gv["fetch_status"].values())


def test_directions_add_up_to_route(synthetic):
    """Turn-by-turn steps cover the whole route: distances and times sum to the route totals."""
    from app.routing import compute_route
    eva = EvaParams.defaults().merged({"eva_hours": 10})
    pts = [(120.005, 10.012), (120.03, 10.03), (120.012, 10.085)]
    r = compute_route(synthetic, pts, eva, "fastest")
    steps = r["directions"]
    assert steps and all(s["instruction"] for s in steps)
    assert abs(sum(s["distance_m"] for s in steps) - r["distance_km"] * 1000) <= len(steps) + 1
    assert abs(sum(s["duration_min"] for s in steps) - r["duration_min"]) <= 0.1 * len(steps) + 0.2
    assert sum(1 for s in steps if s.get("arrive_stop")) == len(pts) - 1


def test_point_info_explains_walkability(synthetic):
    """A steep cell is reported as not walkable with the rule that excludes it; a flat one is walkable."""
    from app.point_info import point_info
    eva = EvaParams.defaults()
    sl = synthetic.slope
    r, c = np.unravel_index(int(np.nanargmax(sl)), sl.shape)
    lon, lat = synthetic.grid.center_of(int(r), int(c))
    info = point_info(synthetic, lon, lat, eva)
    assert info["walkable"] is False and any("slope" in x for x in info["not_walkable_because"])
    r, c = np.unravel_index(int(np.nanargmin(sl)), sl.shape)
    lon, lat = synthetic.grid.center_of(int(r), int(c))
    assert point_info(synthetic, lon, lat, eva)["terrain"]["slope_deg"] <= eva.max_slope_deg


def test_search_names_sols_and_coordinates(synthetic):
    from app import search
    d = search.search(synthetic, "sol 5")
    assert d["results"] and d["results"][0]["kind"] == "rover_sol" or d["count"] == 0
    d = search.search(synthetic, "120.03, 10.03")
    assert d["results"][0]["kind"] == "coordinates" and d["results"][0]["inside_region"] is True
    assert search.search(synthetic, "zzqqxx")["results"] == []


def test_ground_view_image_rejects_bad_ids():
    """Cached-image lookup only accepts plain NASA image ids and known sizes (no path traversal)."""
    from app import rover_images
    for bad in ("../secret", "..\\x", "a/b", "", "ok id"):
        assert rover_images.local_image(bad, "small") is None
    assert rover_images.local_image("ZL0_0001", "huge") is None


def test_assistant_rag_cites_and_refuses(tmp_path, monkeypatch):
    """Hybrid/BM25 retrieval answers from the documents with citations and refuses off-topic questions."""
    from app import assistant
    (tmp_path / "a.txt").write_text("Wildcat Ridge is a fine-grained mudstone. SHERLOC recorded abundant organic "
                                    "molecules there, correlated with sulfate minerals. " * 6, encoding="utf-8")
    (tmp_path / "docs.json").write_text(json.dumps([{"file": "a.txt", "title": "Wildcat Ridge", "url": "https://x",
                                                     "date": "2022", "licence": "test"}]), encoding="utf-8")
    monkeypatch.setattr(assistant, "INDEX", tmp_path / "idx.json")
    monkeypatch.setattr(assistant, "INDEX_EMB", tmp_path / "emb.npy")
    monkeypatch.setattr(assistant, "_internal_docs", lambda: [])
    monkeypatch.setattr(assistant.config, "ANTHROPIC_API_KEY", "")
    info = assistant.build_index(tmp_path, tmp_path / "idx.json", embed=False)
    assert info["chunks"] >= 1
    r = assistant.ask("Which mudstone had organic molecules with sulfate minerals?")
    assert r["found"] and r["citations"] and "[1]" in r["answer"]
    assert assistant.ask("capital city of France")["found"] is False
    assert assistant._sentences("Named after Octavia E. Butler. Next sentence.")[0].endswith("Butler.")


def test_grounding_check_removes_unsupported_claims(monkeypatch):
    """The hallucination guard keeps cited, supported sentences and drops uncited ones and invented numbers."""
    from app import assistant
    monkeypatch.setattr(assistant, "_embedder", lambda: None)  # keyword-support mode, no model needed
    hits = [{"text": "SHERLOC recorded the most abundant organic detections at Wildcat Ridge, a sulfate-bearing mudstone."},
            {"text": "Perseverance landed in Jezero crater in February 2021."}]
    answer = ("SHERLOC recorded abundant organic detections at Wildcat Ridge [1]. "
              "Perseverance landed in Jezero crater in 2021 [2]. "
              "The rock is 3.8 billion years old [1]. "
              "Life was definitely found there.")
    g = assistant.grounding_check(answer, hits)
    assert g["supported"] == 2 and g["total"] == 4
    reasons = " ".join(d["reason"] for d in g["removed"])
    assert "no citation" in reasons and "numbers not in cited sources" in reasons
    assert "billion" not in g["answer"] and "definitely" not in g["answer"]


def test_llm_answer_path_with_mocked_gemini(tmp_path, monkeypatch):
    """With a (mocked) Gemini reply the assistant returns the grounded answer and reports the provider."""
    from app import assistant, config, llm, netutil
    (tmp_path / "a.txt").write_text("Wildcat Ridge is a fine-grained mudstone. SHERLOC recorded abundant organic "
                                    "molecules there, correlated with sulfate minerals. " * 6, encoding="utf-8")
    (tmp_path / "docs.json").write_text(json.dumps([{"file": "a.txt", "title": "WR", "url": "https://x",
                                                     "date": "2022", "licence": "test"}]), encoding="utf-8")
    monkeypatch.setattr(assistant, "INDEX", tmp_path / "idx.json")
    monkeypatch.setattr(assistant, "INDEX_EMB", tmp_path / "emb.npy")
    monkeypatch.setattr(assistant, "_internal_docs", lambda: [])
    monkeypatch.setattr(assistant, "_embedder", lambda: None)
    assistant.build_index(tmp_path, tmp_path / "idx.json", embed=False)
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(netutil, "is_online", lambda *a, **k: True)
    monkeypatch.setattr(llm, "generate", lambda s, u, max_tokens=500: (
        "Wildcat Ridge is a fine-grained mudstone with organic molecules correlated with sulfate minerals [1].",
        "gemini", "gemini-test-flash"))
    r = assistant.ask("Which mudstone had organic molecules with sulfate minerals?")
    assert r["mode"] == "llm" and r["provider"] == "gemini" and r["grounding"]["supported"] == 1


def test_citation_styles_are_normalised(monkeypatch):
    """Gemini-style citations ([1, 2], [1-2], citation after the full stop) still pass the grounding check."""
    from app import assistant
    monkeypatch.setattr(assistant, "_embedder", lambda: None)
    hits = [{"text": "SHERLOC recorded organic detections at Wildcat Ridge."},
            {"text": "Wildcat Ridge is a sulfate-bearing mudstone."}]
    assert assistant._normalise_citations("A claim. [1, 2]", 2) == "A claim [1][2]."
    assert assistant._normalise_citations("A claim [1-2].", 2) == "A claim [1][2]."
    g = assistant.grounding_check("SHERLOC recorded organic detections at Wildcat Ridge. [1] "
                                  "Wildcat Ridge is a sulfate-bearing mudstone. [1, 2]", hits)
    assert g["supported"] == 2 and g["total"] == 2


def test_terrain_patch_is_real_and_bounded(synthetic):
    from app.point_info import terrain_patch
    lon, lat = synthetic.grid.center_of(synthetic.grid.height // 2, synthetic.grid.width // 2)
    p = terrain_patch(synthetic, lon, lat, EvaParams.defaults(), size_m=200, n=12)
    assert len(p["elevation_grid_m"]) == 12 and len(p["elevation_grid_m"][0]) == 12
    assert 0.0 <= p["walkable_fraction"] <= 1.0
    assert sum(p["slope_histogram"]["counts"]) > 0
    assert p["slope_deg"]["min"] <= p["slope_deg"]["max"]


def test_weather_is_honest_without_data(synthetic):
    """No MEDA summary for a region: the weather API says so instead of inventing values."""
    from app import weather
    w = weather.for_site(synthetic, site_id="test-site-01")
    assert w["available"] is False and "reason" in w
    assert weather.all_sites(synthetic)["available"] is False


def test_meda_statistics_use_binned_means():
    """One wild sample must not set the day's maximum: stats come from 5-minute means."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import fetch_meda
    t = np.arange(0, 3600.0)
    v = np.full(t.size, 200.0); v[100] = 900.0
    means, labels = fetch_meda.binned(t, v, ["00001M10:00:00.000"] * t.size)
    s = fetch_meda.stats(means, labels)
    assert s["max"] < 210 and s["min"] == 200.0
    assert fetch_meda.k_to_c(s)["min"] == round(200.0 - 273.15, 1)


def test_packaged_meda_summary_is_physically_plausible():
    """The shipped Jezero MEDA summary: missing data is null (never 0) and values sit in Mars-surface ranges."""
    path = ROOT / "config" / "weather" / "jezero_meda.json"
    if not path.exists():
        pytest.skip("MEDA summary not built")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source_url"].startswith("https://atmos.nmsu.edu/")
    sites = json.loads((ROOT / "config" / "science_sites" / "jezero.geojson").read_text(encoding="utf-8"))
    assert {f["properties"]["id"] for f in sites["features"]} == set(data["sites"])
    ranges = {"air_temp_c": (-120, 35), "ground_temp_c": (-130, 40), "pressure_pa": (400, 1200), "wind_speed_ms": (0, 40)}
    for rec in data["sites"].values():
        for key, (lo, hi) in ranges.items():
            v = rec[key]
            if v is None:
                continue
            assert lo <= v["min"] <= v["mean"] <= v["max"] <= hi, (rec["sol"], key, v)
            assert 0 < v["coverage_h"] <= 24.7


def test_every_assistant_document_has_a_checked_licence():
    """Submission rule: everything used is credited. No document may ship with an unchecked licence."""
    docs = json.loads((ROOT / "data" / "docs" / "docs_sources.json").read_text(encoding="utf-8"))
    for d in docs:
        assert d.get("url", "").startswith("https://"), d.get("title")
        lic = d.get("licence", "")
        assert lic and "confirm" not in lic.lower(), (d["title"], lic)


def test_crew_shares_kit_and_profile_has_walk_home(synthetic):
    """A pair splitting shared kit carries less each, so walks faster; the route profile reports the walk home."""
    from app.routing import compute_route
    a, b = (120.005, 10.012), (120.03, 10.03)
    solo = EvaParams.defaults().merged({"crew_size": 1, "load_kg": 10, "shared_load_kg": 20})
    pair = EvaParams.defaults().merged({"crew_size": 2, "load_kg": 10, "shared_load_kg": 20})
    assert solo.load_per_person_kg == 30 and pair.load_per_person_kg == 20
    r1, r2 = compute_route(synthetic, [a, b], solo, "fastest"), compute_route(synthetic, [a, b], pair, "fastest")
    assert r2["duration_min"] < r1["duration_min"]
    prof = r2["elevation_profile"]
    assert prof[0]["walk_home_min"] == 0 and prof[0]["eta_min"] == 0
    assert all(x["walk_home_min"] <= y["walk_home_min"] + 1e-9 for x, y in zip(prof, prof[1:]))
    assert abs(prof[-1]["walk_home_min"] - r2["return_duration_min"]) <= 0.1
    with pytest.raises(ValueError):
        EvaParams.defaults().merged({"crew_size": 9})


def test_rover_plan_walkback_rule(synthetic):
    """Rover plan: the walk home from each stop matches the walking model, and a tight suit budget triggers R8."""
    from app.reachability import _dijkstra
    from app.rover import compute_rover_plan
    from app.routing import build_masks, snap
    a, b, c = (120.005, 10.012), (120.02, 10.02), (120.03, 10.03)
    eva = EvaParams.defaults().merged({"eva_hours": 6})
    plan = compute_rover_plan(synthetic, [a, b, c], eva, ["Hab", "B", "C"], "pressurized", 10, 30, 10)
    assert plan["drive_km"] > 0 and plan["total_min"] > plan["drive_out_min"]
    assert plan["eva_at_stops_min"] == 2 * (30 + 2 * 10)
    assert plan["longest_suit_time_min"] == 40 and plan["suit_time_within_budget"]
    # walk-back at stop C equals an independent inbound Dijkstra on the walking model
    g = synthetic.grid
    passable, mult = build_masks(synthetic, eva)
    home = snap(synthetic, passable, *a)[0]
    t = _dijkstra(synthetic.elev_flat, passable, mult, g.height, g.width, synthetic.dx_rows, g.dy_m, int(home),
                  eva.flat_speed_ms, eva.max_grade, True, 1e9)
    assert abs(plan["stops"][2]["walkback_min"] - t[snap(synthetic, passable, *c)[0]] / 60) < 0.2
    tight = EvaParams.defaults().merged({"eva_hours": 0.5, "reserve_fraction": 0.0})
    bad = compute_rover_plan(synthetic, [a, c], tight, ["Hab", "C"], "pressurized", 10, 5, 10)
    far_home = bad["stops"][1]["walkback_min"]
    if far_home is not None and far_home > 20:  # walk home longer than 30 min usable minus a 10 min suitport exit
        assert not bad["walkback"]["ok"] and any(w["rule_id"] == "R8_WALKBACK" for w in bad["warnings"])
    # an unpressurized rover uses suit time while driving, so it can never have more margin
    un = compute_rover_plan(synthetic, [a, b, c], eva, ["Hab", "B", "C"], "unpressurized", 10, 30, 10)
    assert un["walkback"]["min_margin_min"] <= plan["walkback"]["min_margin_min"] + 1e-6
    assert un["longest_suit_time_min"] > plan["longest_suit_time_min"]


def test_boulder_shadow_detector_on_synthetic_image():
    """Compact dark shadows of rock size are counted; a long thin shadow and nodata are not."""
    from app.boulders import detect
    rng = np.random.default_rng(1)
    img = (120 + rng.normal(0, 3, (400, 400))).clip(1, 255).astype("uint8")
    for r, c in ((60, 60), (200, 120), (300, 300)):
        img[r:r + 5, c:c + 4] = 40                     # ~1.25 m2 compact shadows
    img[100:103, 150:350] = 40                          # 50 m long scarp shadow: rejected
    img[350:, :50] = 0                                  # nodata corner: ignored
    out = detect(img, 0.25)
    assert len(out["rows"]) == 3
    assert np.all((out["diameter_m"] > 1.0) & (out["diameter_m"] < 1.5))
