"""Prepare a region for Wi-Fi-off use: cache Mars Trek context tiles, the DONKI space-weather window
and the assistant index, then write a zip you can copy to another laptop.

    python backend/scripts/build_offline_package.py jezero
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import netutil, offline  # noqa: E402

if __name__ == "__main__":
    region = sys.argv[1] if len(sys.argv) > 1 else "jezero"
    if netutil.is_online(force_check=True):
        print("online: caching tiles, space weather and assistant index ...")
        print(json.dumps(offline.prefetch(region), indent=2))
    else:
        print("offline: skipping downloads, packaging what is already cached")
    z = offline.build_zip(region)
    print(json.dumps({k: v for k, v in offline.manifest(region).items() if k != "files"}, indent=2))
    print("zip:", z)
