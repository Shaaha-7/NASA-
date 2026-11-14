"""Search: find places by name, Perseverance sols, or coordinates.

Index (per region, built once and cached):
* official IAU place names   config/place_names/<region>.geojson (gazetteer centre coordinates)
* curated science sites     processed science_sites.geojson (incl. sample/core names in the site name)
* geologic units            names from the processed geologic map (where the unit occurs in the study box)
Special queries:
* "sol 509" / "sol509"      Perseverance's localized position on that sol (last waypoint on or before it)
* "77.40, 18.45"            a coordinate pair (lon, lat; east-positive). "18.45 N 77.40 E" also works.
Matching ignores case and accents (Séítah = Seitah) and tolerates small typos.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from functools import lru_cache

import numpy as np

from . import config


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


@lru_cache(maxsize=8)
def _index(region_id: str, folder: str) -> list[dict]:
    from pathlib import Path
    folder = Path(folder)
    items: list[dict] = []

    def add(kind, name, lon, lat, extra=None, aliases=()):
        items.append({"kind": kind, "name": name, "lon": lon, "lat": lat, "extra": extra or {},
                      "keys": [_norm(name)] + [_norm(a) for a in aliases]})

    pn = config.CONFIG_DIR / "place_names" / f"{region_id}.geojson"
    if pn.exists():
        for f in json.loads(pn.read_text(encoding="utf-8")).get("features", []):
            p = f["properties"]
            add("place_name", p["name"], *f["geometry"]["coordinates"][:2],
                {k: p.get(k) for k in ("feature_type", "diameter_km", "source", "source_url")})
    ss = folder / "science_sites.geojson"
    if ss.exists():
        for f in json.loads(ss.read_text(encoding="utf-8")).get("features", []):
            p = f["properties"]
            name = p.get("name", "")
            aliases = re.findall(r"[A-Z][A-Za-z']+(?: [A-Z][A-Za-z']+)*", name)  # e.g. Wildcat Ridge, Hazeltop
            add("science_site", name, *f["geometry"]["coordinates"][:2],
                {k: p.get(k) for k in ("id", "goal_id", "observation_date", "source_url")}, aliases)
    man = folder / "manifest.json"
    terrain = folder / "terrain.npz"
    if man.exists() and terrain.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        units = m.get("units", [])
        if units:
            from .geo import Grid
            g = Grid.from_dict(m["grid"])
            with np.load(terrain) as z:
                codes = z["geo_unit"]
            for u in units:
                rr, cc = np.nonzero(codes == u["code"])
                if rr.size == 0:
                    continue
                k = rr.size // 2  # a representative cell of the unit inside the box
                lon, lat = g.center_of(int(rr[k]), int(cc[k]))
                add("geologic_unit", u["name"], lon, lat,
                    {"walking_time_multiplier": u.get("multiplier"), "flag": u.get("flag"),
                     "share_of_study_box": round(float(rr.size) / codes.size, 3),
                     "note": "location is one representative cell of the unit, not its centre"},
                    aliases=[str(u.get("flag") or "").replace("_", " ")] + (["sand"] if u.get("flag") == "soft_sand" else []))
    return items


def _waypoints(folder) -> list[dict]:
    from pathlib import Path
    f = Path(folder) / "rover_waypoints.geojson"
    if not f.exists():
        return []
    out = []
    for x in json.loads(f.read_text(encoding="utf-8")).get("features", []):
        p = x["properties"]
        op = p.get("original_properties") or {}
        out.append({"sol": int(p.get("sol", 0)), "lon": x["geometry"]["coordinates"][0],
                    "lat": x["geometry"]["coordinates"][1], "rmc": op.get("RMC")})
    return sorted(out, key=lambda w: w["sol"])


def search(region, q: str, limit: int = 10) -> dict:
    q = (q or "").strip()
    g = region.grid
    res: list[dict] = []
    qn = _norm(q)

    m = re.fullmatch(r"\s*sol\s*(\d{1,5})\s*", q, re.I)
    if m:
        sol = int(m.group(1))
        wps = [w for w in _waypoints(str(region.folder)) if w["sol"] <= sol]
        if wps:
            w = wps[-1]
            res.append({"kind": "rover_sol", "name": f"Perseverance on sol {sol}", "lon": w["lon"], "lat": w["lat"],
                        "score": 1.0, "inside_region": g.contains(w["lon"], w["lat"]),
                        "extra": {"localized_sol": w["sol"], "rmc": w["rmc"],
                                  "note": "rover localization on or before that sol (NASA/JPL MMGIS waypoints)"}})
    nums = re.findall(r"-?\d+(?:\.\d+)?", q)
    if not m and len(nums) == 2 and re.fullmatch(r"[\d\s.,;°NnEeSsWw+-]+", q):
        a, b = float(nums[0]), float(nums[1])
        if re.search(r"[Nn]", q) and q.upper().find("N") < q.upper().find("E"):
            lat, lon = a, b  # "18.45 N 77.40 E"
        else:
            lon, lat = a, b  # GeoJSON order
        res.append({"kind": "coordinates", "name": f"{lon:.5f} E, {lat:.5f} N", "lon": lon, "lat": lat, "score": 1.0,
                    "inside_region": g.contains(lon, lat), "extra": {"order": "lon, lat (east-positive)"}})

    if qn and not res:
        for it in _index(region.region_id, str(region.folder)):
            best = 0.0
            for k in it["keys"]:
                if not k:
                    continue
                if k == qn:
                    s = 1.0
                elif k.startswith(qn) or f" {qn}" in f" {k}":
                    s = 0.9
                elif qn in k:
                    s = 0.75
                else:
                    s = difflib.SequenceMatcher(None, qn, k).ratio() * 0.8
                    s = max(s, max((difflib.SequenceMatcher(None, qn, t).ratio() * 0.85 for t in k.split()), default=0))
                best = max(best, s)
            if best >= 0.65:
                res.append({"kind": it["kind"], "name": it["name"], "lon": it["lon"], "lat": it["lat"],
                            "score": round(best, 3), "inside_region": g.contains(it["lon"], it["lat"]),
                            "extra": it["extra"]})
    order = {"science_site": 0, "place_name": 1, "geologic_unit": 2}
    res.sort(key=lambda r: (-r["score"], order.get(r["kind"], 3), r["name"]))
    return {"query": q, "results": res[:limit], "count": len(res),
            "note": "Coordinates are [lon, lat], east-positive. inside_region=false means outside the study box "
                    "(routes and terrain values are only available inside it)."}
