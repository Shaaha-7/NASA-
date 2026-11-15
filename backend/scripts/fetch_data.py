"""Download the Jezero datasets into data/raw/jezero/ (run on a machine with internet).

    python backend/scripts/fetch_data.py            # essentials (CTX DEM, CTX ortho, HiRISE DTM, rover GeoJSON)
    python backend/scripts/fetch_data.py --all      # + SIM 3464 geologic map database (~350 MB)
    python backend/scripts/fetch_data.py --small    # only the small files (no 1.8 GB HiRISE DTM)

Files that already exist with the right size are skipped, so you can re-run safely.
If a URL fails, the script prints the dataset page so you can download it by hand into the same folder.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "jezero"

DATASETS = [
    {"name": "CTX DEM 20 m (Mars 2020 science investigation mosaic)", "size": "small", "essential": True,
     "urls": ["https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif"],
     "page": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/Jez_MARS2020_CTX_DEM_Science_Mosaic"},
    {"name": "CTX orthomosaic 6 m (Mars 2020 TRN)", "size": "medium", "essential": True,
     "urls": ["https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif"],
     "page": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0"},
    {"name": "HiRISE DTM mosaic 1 m (Mars 2020 TRN, ~1.8 GB)", "size": "large", "essential": True,
     "urls": ["https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif"],
     "page": "https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_hirise_dtm_mosaic"},
    {"name": "Perseverance waypoints (GeoJSON)", "size": "small", "essential": True,
     "urls": ["https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"],
     "page": "https://science.nasa.gov/mission/mars-2020-perseverance/location-map/"},
    {"name": "Perseverance traverse (GeoJSON)", "size": "small", "essential": True,
     "urls": ["https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json"],
     "page": "https://science.nasa.gov/mission/mars-2020-perseverance/location-map/"},
    {"name": "CRISM carbonate browse map HRL000040FF (.img)", "size": "small", "essential": True,
     "urls": ["https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/browse/2007/2007_029/hrl000040ff/hrl000040ff_07_brcarj_mtr3.img"],
     "page": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm"},
    {"name": "CRISM carbonate browse map HRL000040FF (.hdr)", "size": "small", "essential": True,
     "urls": ["https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/browse/2007/2007_029/hrl000040ff/hrl000040ff_07_brcarj_mtr3.hdr"],
     "page": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm"},
    {"name": "CRISM carbonate browse map HRL000040FF (.lbl)", "size": "small", "essential": True,
     "urls": ["https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/browse/2007/2007_029/hrl000040ff/hrl000040ff_07_brcarj_mtr3.lbl"],
     "page": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm"},
    {"name": "CRISM mafic browse map HRL000040FF (.img)", "size": "small", "essential": True,
     "urls": ["https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/browse/2007/2007_029/hrl000040ff/hrl000040ff_07_brmafj_mtr3.img"],
     "page": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm"},
    {"name": "CRISM mafic browse map HRL000040FF (.hdr)", "size": "small", "essential": True,
     "urls": ["https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/browse/2007/2007_029/hrl000040ff/hrl000040ff_07_brmafj_mtr3.hdr"],
     "page": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm"},
    {"name": "CRISM mafic browse map HRL000040FF (.lbl)", "size": "small", "essential": True,
     "urls": ["https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/browse/2007/2007_029/hrl000040ff/hrl000040ff_07_brmafj_mtr3.lbl"],
     "page": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm"},
    {"name": "USGS SIM 3464 geologic map database (~350 MB zip, includes THEMIS day/night IR)", "size": "large",
     "essential": False, "unzip": True,
     "urls": ["https://pubs.usgs.gov/sim/3464/sim3464_database.zip", "https://pubs.usgs.gov/sim/3464/sim3464_gis.zip",
              "https://pubs.usgs.gov/sim/3464/sim3464.zip"],
     "page": "https://pubs.usgs.gov/publication/sim3464  (click 'Database (349.3 MB zip)')"},
]


def download(url: str, dest: Path) -> bool:
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(30, read=120)) as r:
            if r.status_code != 200:
                print(f"    HTTP {r.status_code} for {url}")
                return False
            total = int(r.headers.get("content-length", 0))
            if dest.exists() and total and dest.stat().st_size == total:
                print("    already downloaded, skipping")
                return True
            tmp = dest.with_suffix(dest.suffix + ".part")
            done = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r    {done/1e6:8.1f} / {total/1e6:.1f} MB", end="", flush=True)
            print()
            tmp.replace(dest)
            return True
    except Exception as e:
        print(f"    failed: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="also download the geologic map database")
    ap.add_argument("--small", action="store_true", help="skip the 1.8 GB HiRISE DTM")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    for d in DATASETS:
        if not d["essential"] and not a.all:
            continue
        if a.small and d["size"] == "large":
            continue
        print(f"\n== {d['name']}")
        ok = False
        for url in d["urls"]:
            dest = OUT / url.rsplit("/", 1)[1]
            print(f"    {url}")
            if download(url, dest):
                ok = True
                if d.get("unzip"):
                    print("    unzipping ...")
                    with zipfile.ZipFile(dest) as z:
                        z.extractall(OUT / dest.stem)
                break
        if not ok:
            failed.append(d)
    print("\n" + "=" * 70)
    if failed:
        print("Download these by hand into", OUT)
        for d in failed:
            print(f" - {d['name']}\n   {d['page']}")
        print("(Zip files: unzip them inside that folder. File names do not need to change.)")
    else:
        print("All requested files downloaded to", OUT)
    print("Next: python backend/scripts/prepare_data.py jezero")


if __name__ == "__main__":
    sys.exit(main())
