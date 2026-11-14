"""Download the assistant's document corpus listed in data/docs/docs_sources.json (needs internet),
write data/docs/docs.json (title, url, date, licence per file) and build the search index.

    python backend/scripts/fetch_docs.py

Add more public NASA/USGS documents by adding entries to docs_sources.json (or drop files into
data/docs and add them to docs.json by hand), then run build_assistant_index.py.
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import assistant  # noqa: E402

DOCS = ROOT / "data" / "docs"


def main():
    sources = json.loads((DOCS / "docs_sources.json").read_text(encoding="utf-8"))
    meta_path = DOCS / "docs.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else []
    have = {m["file"] for m in meta}
    for s in sources:
        dest = DOCS / s["file"]
        if not dest.exists():
            print("downloading", s["url"])
            try:
                r = httpx.get(s["url"], follow_redirects=True, timeout=60,
                              headers={"User-Agent": "Mozilla/5.0 MarsPath-docs-fetch"})
                r.raise_for_status()
                dest.write_bytes(r.content)
            except Exception as e:
                print("   failed:", e)
                continue
        if s["file"] not in have:
            meta.append({k: s[k] for k in ("file", "title", "url", "date", "licence")})
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(assistant.build_index())


if __name__ == "__main__":
    main()
