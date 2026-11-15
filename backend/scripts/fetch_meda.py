"""Download Perseverance MEDA weather for the sols of the curated science sites and summarise it.

Source: NASA PDS Atmospheres node, Mars 2020 MEDA bundle
  https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/
Files per sol (version suffix P0x varies, so each folder is listed first):
  data_calibrated_env  CAL_ATS   air temperature sensors (K)
  data_calibrated_env  CAL_TIRS  ground temperature (K)
  data_derived_env     DER_PS    pressure (Pa)
  data_derived_env     DER_WS    wind speed (m/s), only on sols where the wind sensor produced data
Raw CSVs go to <data>/raw/<region>/meda/ (git-ignored). The small summary goes to
config/weather/<region>_meda.json (committed), so every teammate has it without downloading.

Statistics use 5-minute means (not single samples), so a noisy sample cannot set a minimum or maximum.
Missing files or columns give null, never a made-up number.

    python backend/scripts/fetch_meda.py [region_id]
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import config  # noqa: E402

BASE = "https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda"
UA = {"User-Agent": "Mozilla/5.0 MarsPath-meda-fetch"}
RANGES = [(0, 89), (90, 179)] + [(a, a + 119) for a in range(180, 3000, 120)]
PRODUCTS = {"ATS": ("data_calibrated_env", "CAL_ATS"), "TIRS": ("data_calibrated_env", "CAL_TIRS"),
            "PS": ("data_derived_env", "DER_PS"), "WS": ("data_derived_env", "DER_WS")}
BAD = 9e8


def sol_dir(collection: str, sol: int) -> str:
    a, b = next(r for r in RANGES if r[0] <= sol <= r[1])
    return f"{BASE}/{collection}/sol_{a:04d}_{b:04d}/sol_{sol:04d}/"


def fetch(sol: int, key: str, out_dir: Path) -> tuple[Path | None, str | None]:
    collection, tag = PRODUCTS[key]
    url = sol_dir(collection, sol)
    try:
        listing = httpx.get(url, headers=UA, timeout=60, follow_redirects=True)
        if listing.status_code != 200:
            return None, None
        names = sorted(set(re.findall(rf"WE__{sol:04d}_+{tag}_+P\d+\.CSV", listing.text)))
        if not names:
            return None, None
        name = names[-1]  # highest version
        dest = out_dir / name
        if not dest.exists() or dest.stat().st_size < 1000:
            r = httpx.get(url + name, headers=UA, timeout=180, follow_redirects=True)
            r.raise_for_status()
            dest.write_bytes(r.content)
        return dest, url + name
    except Exception as e:
        print(f"   {key} sol {sol}: {str(e).splitlines()[0][:100]}")
        return None, None


def read_cols(path: Path, cols: list[str]) -> tuple[np.ndarray, dict[str, np.ndarray], list[str]]:
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        rd = csv.reader(f)
        head = next(rd)
        idx = {c: head.index(c) for c in cols if c in head}
        t, lmst, vals = [], [], {c: [] for c in idx}
        for row in rd:
            try:
                t.append(float(row[0]))
            except (ValueError, IndexError):
                continue
            lmst.append(row[1] if len(row) > 1 else "")
            for c, i in idx.items():
                try:
                    v = float(row[i])
                    vals[c].append(v if abs(v) < BAD else np.nan)
                except (ValueError, IndexError):
                    vals[c].append(np.nan)
    return np.array(t), {c: np.array(v) for c, v in vals.items()}, lmst


def binned(t: np.ndarray, v: np.ndarray, lmst: list[str], width_s: float = 300.0):
    """5-minute means: returns (means, LMST label of each bin)."""
    ok = np.isfinite(v)
    if ok.sum() < 10:
        return np.array([]), []
    b = ((t - t[ok][0]) // width_s).astype(int)
    means, labels = [], []
    for k in np.unique(b[ok]):
        m = ok & (b == k)
        if m.sum() >= 5:
            means.append(float(np.mean(v[m])))
            lab = lmst[int(np.flatnonzero(m)[0])]
            labels.append(lab.split("M")[-1][:5] if "M" in lab else "")
    return np.array(means), labels


def stats(means: np.ndarray, labels: list[str], digits: int = 1) -> dict | None:
    if means.size == 0:
        return None
    i0, i1 = int(np.argmin(means)), int(np.argmax(means))
    return {"min": round(float(means[i0]), digits), "max": round(float(means[i1]), digits),
            "mean": round(float(means.mean()), digits), "min_lmst": labels[i0], "max_lmst": labels[i1],
            "coverage_h": round(means.size * 5 / 60, 1)}


def k_to_c(s: dict | None) -> dict | None:
    if not s:
        return None
    return {**s, "min": round(s["min"] - 273.15, 1), "max": round(s["max"] - 273.15, 1), "mean": round(s["mean"] - 273.15, 1)}


def summarise(sol: int, out_dir: Path) -> dict:
    rec = {"sol": sol, "files": {}}
    p, u = fetch(sol, "ATS", out_dir)
    if p:
        t, v, lm = read_cols(p, [f"ATS_LOCAL_TEMP{i}" for i in range(1, 6)])
        if v:
            med = np.nanmedian(np.vstack(list(v.values())), axis=0)
            rec["air_temp_c"] = k_to_c(stats(*binned(t, med, lm)))
            rec["files"]["air_temp"] = u
    p, u = fetch(sol, "TIRS", out_dir)
    if p:
        t, v, lm = read_cols(p, ["GROUND_TEMP"])
        if "GROUND_TEMP" in v:
            rec["ground_temp_c"] = k_to_c(stats(*binned(t, v["GROUND_TEMP"], lm)))
            rec["files"]["ground_temp"] = u
    p, u = fetch(sol, "PS", out_dir)
    if p:
        t, v, lm = read_cols(p, ["PRESSURE"])
        if "PRESSURE" in v:
            rec["pressure_pa"] = stats(*binned(t, v["PRESSURE"], lm), digits=0)
            rec["files"]["pressure"] = u
    p, u = fetch(sol, "WS", out_dir)
    if p:
        t, v, lm = read_cols(p, ["HORIZONTAL_WIND_SPEED"])
        if "HORIZONTAL_WIND_SPEED" in v:
            rec["wind_speed_ms"] = stats(*binned(t, v["HORIZONTAL_WIND_SPEED"], lm))
            rec["files"]["wind"] = u
    for k in ("air_temp_c", "ground_temp_c", "pressure_pa", "wind_speed_ms"):
        rec.setdefault(k, None)
    return rec


def main() -> int:
    region_id = sys.argv[1] if len(sys.argv) > 1 else "jezero"
    sites_file = ROOT / "config" / "science_sites" / f"{region_id}.geojson"
    if not sites_file.exists():
        print(f"No {sites_file}")
        return 1
    out_dir = config.RAW_DIR / region_id / "meda"
    out_dir.mkdir(parents=True, exist_ok=True)
    sites = json.loads(sites_file.read_text(encoding="utf-8"))["features"]
    records = {}
    for f in sites:
        p = f["properties"]
        m = re.search(r"sol (\d+)", str(p.get("observation_date", "")))
        m2 = re.search(r"\(sol (\d+)\)", str(p.get("position_basis", "")))
        sol = int(m.group(1)) if m else None
        if sol in (None, 0) and m2:
            sol = int(m2.group(1))  # landing sol has no weather yet: use the first localized sol
        if sol is None:
            continue
        print(f"{p['id']} sol {sol} ...")
        rec = summarise(sol, out_dir)
        rec["site_name"] = p.get("name")
        records[p["id"]] = rec
        print("   ", {k: (rec[k] and (rec[k]["min"], rec[k]["max"])) for k in ("air_temp_c", "ground_temp_c", "pressure_pa", "wind_speed_ms")})
    out = {
        "region_id": region_id,
        "source": "Mars 2020 Perseverance MEDA (Mars Environmental Dynamics Analyzer), NASA PDS Atmospheres node",
        "source_url": f"{BASE}/",
        "method": "Per sol: minimum, maximum and mean of 5-minute means. Air temperature = median of the five ATS "
                  "sensors (calibrated); ground temperature = TIRS (calibrated); pressure and wind = derived products.",
        "notes": ["Historical measurements at the rover on that sol, not live conditions and not a forecast.",
                  "Wind is only available on sols where the wind sensors returned valid data.",
                  "A sol's record may not cover all 24 hours: see coverage_h."],
        "sites": records,
    }
    dest = ROOT / "config" / "weather" / f"{region_id}_meda.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
