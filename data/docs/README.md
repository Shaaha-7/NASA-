# Assistant documents

1. Online: `python backend/scripts/fetch_docs.py` downloads every file listed in `docs_sources.json`,
   writes `docs.json`, and builds the index.
2. To add your own: put the file here (.pdf, .txt, .md, .html), add an entry to `docs.json`
   with file, title, url, date and licence, then run `python backend/scripts/build_assistant_index.py`.

Only public material. Each document's licence is recorded in `docs_sources.json` (all checked 2026-11-15). The documents are downloaded by `fetch_docs.py` on each machine and are not stored in this repository.
