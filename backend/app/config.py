"""Paths and settings. Everything can be overridden with environment variables
(or a .env-style set in run.bat) so the same code runs online and offline."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(os.environ.get("MARSPATH_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_DIR = ROOT / "config"
REGIONS_CONFIG_DIR = CONFIG_DIR / "regions"
DATA_DIR = Path(os.environ.get("MARSPATH_DATA", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DOCS_DIR = DATA_DIR / "docs"
MISSIONS_DIR = DATA_DIR / "missions"
CACHE_DIR = DATA_DIR / "cache"
FRONTEND_DIR = ROOT / "frontend"

# NASA open APIs (DONKI). DEMO_KEY works but is heavily rate-limited.
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

# Optional LLM for the assistant. With no key the assistant still works:
# it returns the best-matching passages with citations (extractive mode).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("MARSPATH_LLM_MODEL", "claude-sonnet-5-5")
# Google Gemini (preferred when GEMINI_API_KEY is set). Leave GEMINI_MODEL empty to let MarsPath pick a
# current "flash" model from the models your key can use (listed via the Gemini API, not guessed).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")
LLM_PROVIDER = "gemini" if GEMINI_API_KEY else ("anthropic" if ANTHROPIC_API_KEY else "none")

# When set to 1 the backend never calls the network (forces offline behaviour,
# useful to rehearse the Wi-Fi-off demo).
FORCE_OFFLINE = os.environ.get("MARSPATH_OFFLINE", "0") == "1"

# Mars Trek WMTS (equirectangular) tile template. {layer} {z} {y} {x}.
TREK_TILE_TEMPLATE = os.environ.get(
    "MARSPATH_TREK_TEMPLATE",
    "https://trek.nasa.gov/tiles/Mars/EQ/{layer}/1.0.0/default/default028mm/{z}/{y}/{x}.{ext}",
)
TREK_LAYERS = {
    # id: (trek layer name, file extension, label, mission, instrument, resolution)
    # Add more layers after checking their exact names in the Trek WMTSCapabilities.xml
    # (https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars).
    "mola_shade": ("Mars_MGS_MOLA_ClrShade_merge_global_463m", "jpg",
                   "MOLA colour hillshade (global context)", "Mars Global Surveyor", "MOLA", "463 m/px"),
}
TREK_SOURCE_URL = "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars"

for d in (PROCESSED_DIR, MISSIONS_DIR, CACHE_DIR, DOCS_DIR, RAW_DIR):
    d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def eva_defaults() -> dict:
    with open(CONFIG_DIR / "eva_defaults.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def geo_penalties() -> dict:
    with open(CONFIG_DIR / "geo_penalties.json", encoding="utf-8") as f:
        return json.load(f)


def region_config(region_id: str) -> dict | None:
    p = REGIONS_CONFIG_DIR / f"{region_id}.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)
