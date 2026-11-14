"""AI science assistant (RAG) that answers ONLY from preloaded documents and always cites them.

Retrieval: BM25 keyword search over ~350-word chunks. Pure Python, no model download, works
fully offline. Generation: if ANTHROPIC_API_KEY is set and the machine is online, an LLM writes
a short answer from the retrieved chunks only. Otherwise the assistant answers in
"extractive" mode: the best passages, quoted with their sources.

Corpus: put files in data/docs/ (.txt, .md, .html, .pdf) and describe each in data/docs/docs.json:
  [{"file": "sim3464_pamphlet.pdf", "title": "...", "url": "...", "date": "2020", "licence": "public domain"}]
Then run:  python backend/scripts/build_assistant_index.py
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from . import config, netutil

INDEX = config.CACHE_DIR / "assistant_index.json"
STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was were with
which what who how why when where do does did can could should would about into over than then there these those
their they them we you your our not no yes also may might will just more most such near""".split())
GUARDRAIL = ("You are the MarsPath science assistant for a Mars EVA planning tool. Answer ONLY from the numbered "
             "source passages provided. Cite every claim with [n] using the passage numbers. If the passages do not "
             "contain the answer, reply exactly: NOT_IN_DOCUMENTS. Keep the answer to 2-5 sentences. Do not use outside knowledge.")


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower()) if t not in STOP and len(t) > 1]


def _read(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    text = path.read_text(encoding="utf-8", errors="ignore")
    if suf in (".html", ".htm"):
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
    return text


def _chunks(text: str, size=350, overlap=60) -> list[str]:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + size]))
        i += size - overlap
    return [c for c in out if len(c) > 80]


def build_index(docs_dir: Path | None = None, out: Path | None = None) -> dict:
    docs_dir = docs_dir or config.DOCS_DIR
    out = out or INDEX
    meta_path = docs_dir / "docs.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else []
    by_file = {m["file"]: m for m in meta if "file" in m}
    chunks, skipped = [], []
    for p in sorted(docs_dir.iterdir()):
        if p.name == "docs.json" or p.name.startswith(".") or p.name.lower().startswith("readme") or \
                p.suffix.lower() not in (".txt", ".md", ".html", ".htm", ".pdf"):
            continue
        m = by_file.get(p.name)
        if not m:
            skipped.append(f"{p.name} (no entry in docs.json: title/url/date/licence are required)")
            continue
        try:
            text = _read(p)
        except Exception as e:
            skipped.append(f"{p.name} ({e})")
            continue
        for k, c in enumerate(_chunks(text)):
            chunks.append({"doc": p.name, "title": m.get("title", p.name), "url": m.get("url"), "date": m.get("date"),
                           "licence": m.get("licence"), "chunk": k, "text": c, "tokens": _tokens(c)})
    df = Counter()
    for c in chunks:
        df.update(set(c["tokens"]))
    idx = {"n": len(chunks), "avgdl": (sum(len(c["tokens"]) for c in chunks) / len(chunks)) if chunks else 0,
           "df": dict(df), "chunks": chunks, "docs": sorted({c["doc"] for c in chunks}), "skipped": skipped}
    out.write_text(json.dumps(idx), encoding="utf-8")
    return {"chunks": len(chunks), "documents": idx["docs"], "skipped": skipped}


_loaded: dict = {}


def _index() -> dict | None:
    if not INDEX.exists():
        return None
    mt = INDEX.stat().st_mtime
    if _loaded.get("mtime") != mt:
        _loaded["idx"] = json.loads(INDEX.read_text(encoding="utf-8"))
        _loaded["mtime"] = mt
    return _loaded["idx"]


def search(query: str, k: int = 4, idx: dict | None = None) -> list[dict]:
    idx = idx or _index()
    if not idx or not idx["n"]:
        return []
    q = _tokens(query)
    N, avg, k1, b = idx["n"], idx["avgdl"] or 1, 1.5, 0.75
    scored = []
    for c in idx["chunks"]:
        tf = Counter(c["tokens"])
        dl = len(c["tokens"])
        s = 0.0
        for t in q:
            if t in tf:
                n = idx["df"].get(t, 0)
                s += math.log(1 + (N - n + 0.5) / (n + 0.5)) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / avg))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [{**c, "score": round(s, 3)} for s, c in scored[:k]]


def ask(question: str, region_name: str | None = None, lon: float | None = None, lat: float | None = None,
        min_score: float = 2.0) -> dict:
    q = question.strip()
    if not q:
        raise ValueError("empty question")
    idx = _index()
    if not idx or not idx["n"]:
        return {"found": False, "mode": "none", "answer": "The document library is empty. Add NASA documents to "
                "data/docs and run build_assistant_index.py.", "citations": []}
    hits = [h for h in search(q + (" " + region_name if region_name else ""), k=4, idx=idx) if h["score"] >= min_score]
    if not hits:
        return {"found": False, "mode": "retrieval", "answer": "Not found in the loaded documents.", "citations": []}
    cites = [{"n": i + 1, "title": h["title"], "url": h["url"], "date": h["date"], "doc": h["doc"],
              "score": h["score"], "snippet": h["text"][:400] + ("..." if len(h["text"]) > 400 else "")}
             for i, h in enumerate(hits)]
    if config.ANTHROPIC_API_KEY and netutil.is_online():
        try:
            ctx = "\n\n".join(f"[{i+1}] ({h['title']})\n{h['text']}" for i, h in enumerate(hits))
            where = f" The user is looking at lon {lon:.4f} E, lat {lat:.4f} N." if lon is not None and lat is not None else ""
            import httpx
            r = httpx.post("https://api.anthropic.com/v1/messages", timeout=40,
                           headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                                    "content-type": "application/json"},
                           json={"model": config.LLM_MODEL, "max_tokens": 400, "system": GUARDRAIL,
                                 "messages": [{"role": "user", "content": f"Sources:\n{ctx}\n\nQuestion: {q}{where}"}]})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []))
            if "NOT_IN_DOCUMENTS" in text:
                return {"found": False, "mode": "llm", "answer": "Not found in the loaded documents.", "citations": cites}
            return {"found": True, "mode": "llm", "answer": text.strip(), "citations": cites}
        except Exception as e:
            fallback_note = f" (LLM unavailable: {str(e)[:120]})"
    else:
        fallback_note = ""
    best = hits[0]["text"]
    sents = re.split(r"(?<=[.!?])\s+", best)
    qt = set(_tokens(q))
    ranked = sorted(sents, key=lambda s: -len(qt & set(_tokens(s))))[:3]
    answer = " ".join(s for s in sents if s in ranked)[:700] + " [1]"
    return {"found": True, "mode": "extractive", "answer": answer,
            "note": "Extractive answer: the most relevant passage from the documents, not a generated summary." + fallback_note,
            "citations": cites}
