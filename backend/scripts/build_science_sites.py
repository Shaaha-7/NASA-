"""Build config/science_sites/jezero.geojson from verified Perseverance sample sites.

Positions are NOT typed by hand. Each site's position is the rover's own localization
(NASA/JPL MMGIS M20_waypoints.json) at the last waypoint on or before the sol the sample
was taken. Sols come from published sources (NASA sample table, peer-reviewed papers) or,
where only an Earth date is published, from date -> sol (landing 2021-02-18 20:55 UTC,
1 sol = 1.02749125 days). That conversion reproduces every independently published sol
we checked: Salette 262, Coulettes 271, Swift Run 490, Skyland 495, Hazeltop 509,
Bearwallow 516, first depot drop 653.

    python backend/scripts/build_science_sites.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAYPOINTS = ROOT / "data" / "raw" / "jezero" / "M20_waypoints.json"
OUT = ROOT / "config" / "science_sites" / "jezero.geojson"
LANDING = dt.datetime(2021, 2, 18, 20, 55, tzinfo=dt.timezone.utc)
SOL_DAYS = 1.02749125

NASA_SAMPLES = ("NASA Mars 2020: Mars Rock Samples", "https://science.nasa.gov/mission/mars-2020-perseverance/mars-rock-samples/")
WAYPOINTS_SRC = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"

SITES = [
    dict(id="site-01", name="Octavia E. Butler Landing", goal_id="context", sol=0, date="2021-02-18",
         observation="Perseverance touchdown site, informally named Octavia E. Butler Landing by the science team.",
         instrument="Rover localization",
         why="Start point of the mission and a natural EVA start/return point on flat crater-floor terrain.",
         source="NASA/JPL PIA24483, Welcome to Octavia E. Butler Landing",
         url="https://photojournal.jpl.nasa.gov/catalog/PIA24483"),
    dict(id="site-02", name="Rochette (Montdenier, Montagnac cores)", goal_id="context", date="2021-09-06",
         observation="Site of Perseverance's first two rock cores, Montdenier and Montagnac, from the crater-floor rock "
                     "called Rochette (basalt or basaltic sandstone in NASA's sample table).",
         instrument="Sampling and Caching System; PIXL; SHERLOC",
         why="First cored rocks of the mission: igneous crater-floor context for the walk.",
         source="NASA Science, A Historic Moment: Perseverance collects its first two rock samples",
         url="https://science.nasa.gov/missions/mars-2020-perseverance/a-historic-moment-perseverance-collects-seals-and-stores-its-first-two-rock-samples"),
    dict(id="site-03", name="Brac outcrop, Seitah (Salette, Coulettes cores)", goal_id="G2", sol=262,
         observation="Olivine cumulate rock in the Seitah formation; cores Salette (sol 262) and Coulettes (sol 271).",
         instrument="PIXL; SHERLOC; SuperCam; Sampling and Caching System",
         why="Olivine-rich igneous rock of the Seitah unit: direct target for goal G2.",
         source="Weiss et al. 2024, Earth and Space Science (sol table); Liu et al. 2022, Science (olivine cumulate)",
         url="https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2023EA003322"),
    dict(id="site-04", name="Issole, Seitah (Robine core)", goal_id="G2", date="2021-12-22",
         observation="Olivine cumulate rock in South Seitah; core Robine.",
         instrument="Sampling and Caching System",
         why="Second Seitah sampling site: compare olivine-rich rock along the walk.",
         source=NASA_SAMPLES[0], url=NASA_SAMPLES[1]),
    dict(id="site-05", name="Skinner Ridge, delta front (Swift Run, Skyland cores)", goal_id="G3", sol=490,
         observation="First sedimentary cores of the mission, Swift Run (sol 490) and Skyland (sol 495), at the base "
                     "of the western fan; the rover arrived on sol 477.",
         instrument="Sampling and Caching System; Mastcam-Z; SuperCam",
         why="Layered sedimentary rock at the fan front: the base of the delta stratigraphy for goal G3.",
         source="Bosak et al. 2024, AGU Advances, Astrobiological potential of rocks at a sedimentary fan front",
         url="https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2024AV001241"),
    dict(id="site-06", name="Wildcat Ridge, delta front (Hazeltop, Bearwallow cores)", goal_id="G1", sol=509,
         observation="Fine-grained, sulfate-bearing mudstone; SHERLOC recorded the mission's most abundant organic "
                     "detections to that date, spatially correlated with sulfate minerals. Cores Hazeltop (sol 509) "
                     "and Bearwallow (sol 516).",
         instrument="SHERLOC; PIXL; Sampling and Caching System",
         why="Organic molecules in a lake-deposited mudstone make it a priority biosignature target (organics with "
             "sulfates, not carbonate).",
         source="NASA/JPL, NASA's Perseverance Rover Investigates Geologically Rich Mars Terrain",
         url="https://www.jpl.nasa.gov/news/nasas-perseverance-rover-investigates-geologically-rich-mars-terrain/"),
    dict(id="site-07", name="Amalik outcrop, delta front (Shuyak core)", goal_id="G3", date="2022-10-02",
         observation="Delta-front sedimentary outcrop; core Shuyak.",
         instrument="Sampling and Caching System; Mastcam-Z",
         why="Another layer of the fan-front sediments, a short walk from Skinner Ridge and Wildcat Ridge.",
         source="NASA Mars 2020 mission status: Perseverance activities at Amalik outcrop",
         url="https://mars.nasa.gov/mars2020/mission/status/415/perseverance-activities-at-amalik-outcrop"),
    dict(id="site-08", name="Three Forks sample depot", goal_id="context", sol=653,
         observation="Ten sample tubes left on the surface between sols 653 and 690 for possible future return to Earth.",
         instrument="Sampling and Caching System",
         why="Mapped depot of cached samples near the base of the delta: a known, flat waypoint.",
         source="NASA, NASA's Perseverance Rover Completes Mars Sample Depot",
         url="https://www.nasa.gov/missions/mars-2020-perseverance/perseverance-rover/nasas-perseverance-rover-completes-mars-sample-depot/"),
    dict(id="site-09", name="Berea, upper fan (Melyn core)", goal_id="G3", date="2023-03-30",
         observation="Sandstone on the upper fan; core Melyn, the first sample after the depot was completed.",
         instrument="Sampling and Caching System",
         why="Upper part of the fan: compare with the fan-front layers to read the delta's history.",
         source=NASA_SAMPLES[0], url=NASA_SAMPLES[1]),
    dict(id="site-10", name="Hans Amundsen Memorial Workspace, margin unit (Pelican Point core)", goal_id="G1",
         date="2023-09-23",
         observation="Core Pelican Point from the margin unit along the inner crater rim; orbital spectra map "
                     "carbonate-bearing rocks along this crater margin.",
         instrument="Sampling and Caching System (sample); MRO CRISM (orbital carbonate mapping)",
         why="Marginal carbonates are a biosignature target for goal G1.",
         source="NASA Mars Rock Samples (core); Zastrow & Glotch 2021, GRL (margin carbonates from orbit)",
         url="https://pmc.ncbi.nlm.nih.gov/articles/PMC8243932"),
]


def sol_of(date: str) -> int:
    t = dt.datetime.fromisoformat(date + "T12:00:00+00:00")
    return int((t - LANDING).total_seconds() / 86400 / SOL_DAYS)


def main() -> int:
    if not WAYPOINTS.exists():
        print(f"Missing {WAYPOINTS}. Run fetch_data.py first.")
        return 1
    wps = sorted((f["properties"] for f in json.loads(WAYPOINTS.read_text(encoding="utf-8"))["features"]),
                 key=lambda p: (p["sol"], p["site"], p["drive"]))
    feats = []
    for s in SITES:
        sol = s["sol"] if "sol" in s else sol_of(s["date"])
        before = [p for p in wps if p["sol"] <= max(sol, wps[0]["sol"])]
        p = before[-1]
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(p["lon"], 7), round(p["lat"], 7)]},
            "properties": {
                "id": s["id"], "kind": "science_site", "name": s["name"], "goal_id": s["goal_id"],
                "observation": s["observation"], "mission": "Mars 2020", "instrument": s["instrument"],
                "observation_date": f"sol {sol}" + (f" ({s['date']})" if s.get("date") else ""),
                "why_it_matters": s["why"], "source": s["source"], "source_url": s["url"],
                "measured_or_derived": "measured (rover localization and published sample records)",
                "position_basis": f"Perseverance localization RMC {p['RMC']} (sol {p['sol']}), last waypoint on or "
                                  f"before sol {sol}; accurate to the rover's workspace (a few metres)",
                "position_source_url": WAYPOINTS_SRC,
                "rover_elevation_m": round(p["elev_geoid"], 2),
                "sample_record_url": NASA_SAMPLES[1],
            },
        })
    OUT.write_text(json.dumps({"type": "FeatureCollection", "name": "Jezero science sites (verified)",
                               "features": feats}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(feats)} sites")
    for f in feats:
        pr = f["properties"]
        print(f"  {pr['id']} {pr['goal_id']:8s} {pr['observation_date']:22s} {f['geometry']['coordinates']}  {pr['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
