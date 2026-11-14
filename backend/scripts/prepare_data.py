"""Prepare one region for MarsPath (crop, align, derive slope/roughness, overlays, hazards).

Usage:
    python backend/scripts/prepare_data.py jezero
    python backend/scripts/prepare_data.py synthetic      (test site, after make_synthetic.py)

Put raw downloads in data/raw/<region_id>/ (sub-folders are fine; files are found by name).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.prepare import prepare_region  # noqa: E402

if __name__ == "__main__":
    region = sys.argv[1] if len(sys.argv) > 1 else "jezero"
    t = time.time()
    prepare_region(region)
    print(f"[prepare] finished in {time.time() - t:.1f} s")
