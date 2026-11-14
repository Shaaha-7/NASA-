"""Download the assistant's document corpus listed in data/docs/docs_sources.json (needs internet),
write docs.json (title, url, date, licence per file), download the local embedding model and
build the hybrid search index.

    python backend/scripts/fetch_docs.py

Files go to the data folder in use (MARSPATH_DATA, default ./data/docs). Add more public NASA/USGS
documents by adding entries to docs_sources.json (or drop files into the docs folder and add them
to docs.json by hand), then run build_assistant_index.py.
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import assistant, config  # noqa: E402

SOURCES = ROOT / "data" / "docs" / "docs_sources.json"
DOCS = config.DOCS_DIR
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36 MarsPath-docs-fetch")


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    meta_path = DOCS / "docs.json"
    old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else []
    listed = {s["file"] for s in sources}
    meta = [m for m in old if m.get("file") not in listed]  # keep hand-added entries
    failed = []
    for s in sources:
        dest = DOCS / s["file"]
        if not dest.exists() or dest.stat().st_size < 500:
            print("downloading", s["url"])
            try:
                r = httpx.get(s["url"], follow_redirects=True, timeout=90, headers={"User-Agent": UA})
                r.raise_for_status()
                dest.write_bytes(r.content)
            except Exception as e:
                print("   failed:", str(e).splitlines()[0][:160])
                failed.append(s["file"])
                continue
        meta.append({k: s[k] for k in ("file", "title", "url", "date", "licence")})
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if failed:
        print("Not downloaded (skipped from the index):", failed)
    print(json.dumps(assistant.build_index(), indent=2))


if __name__ == "__main__":
    main()
