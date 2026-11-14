"""MarsPath science assistant: retrieval-augmented answers ONLY from loaded documents, always cited.

Corpus
* External documents in data/docs/ (.pdf, .html, .txt, .md), each described in data/docs/docs.json
  (file, title, url, date, licence). Download them with backend/scripts/fetch_docs.py.
* MarsPath's own knowledge, generated at index time from the prepared regions: the curated science
  sites (with their sources), every dataset used (mission, instrument, resolution), the EVA model
  assumptions and the rover benchmark. So the assistant can explain the tool's own numbers.

Retrieval (hybrid, fully offline once built)
* BM25 keyword search over ~200-word, sentence-aligned chunks (PDF chunks keep their page number).
* Dense semantic search with a small local embedding model (BAAI/bge-small-en-v1.5 via fastembed,
  ~65 MB, cached in data/cache/models). Brute-force cosine similarity: exact, and fast at this size.
* Reciprocal-rank fusion of both lists. If the embedding model is unavailable, BM25 alone is used and
  the response says so.

Answering
* Online with ANTHROPIC_API_KEY: Claude writes 2-5 sentences from the retrieved passages only, citing
  [n]; citations are checked against the passages actually sent. "NOT_IN_DOCUMENTS" -> not found.
* Otherwise "extractive": the most relevant sentences, each quoted with its [n].
* With a location (lon/lat + region), MarsPath's own terrain/geology readout for that point is added
  as a cited source, labelled as model-derived data rather than literature.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

from . import config, netutil

INDEX = config.CACHE_DIR / "assistant_index.json"
INDEX_EMB = config.CACHE_DIR / "assistant_embeddings.npy"
MODEL_DIR = config.CACHE_DIR / "models"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_WORDS, CHUNK_OVERLAP = 200, 40
RRF_K = 60
COS_FOUND = 0.58      # dense similarity for "relevant": eval on-topic min 0.63, off-topic max 0.52
STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was were with
which what who how why when where do does did can could should would about into over than then there these those
their they them we you your our not no yes also may might will just more most such near tell me""".split())
GUARDRAIL = ("You are the MarsPath science assistant for a Mars EVA (Marswalk) planning tool. Answer ONLY from the "
             "numbered source passages provided. Cite every claim with [n] using the passage numbers. If the passages "
             "do not contain the answer, reply exactly: NOT_IN_DOCUMENTS. Keep the answer to 2-5 sentences. Do not use "
             "outside knowledge. Passages marked 'MarsPath data' are model-derived values from the tool, not literature: "
             "say so when you use them.")


# ---------------------------------------------------------------- text extraction and chunking


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower()) if t not in STOP and len(t) > 1]


def _html_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|form|aside)\b.*?</\1>", " ", html)
    m = re.search(r"(?is)<(article|main)\b.*?</\1>", html)
    body = m.group(0) if m else html
    body = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>|</tr>|</div>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    for a, b in (("&nbsp;", " "), ("&#160;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"),
                 ("&quot;", '"'), ("&rsquo;", "'"), ("&lsquo;", "'"), ("&ldquo;", '"'), ("&rdquo;", '"'),
                 ("&ndash;", "-"), ("&mdash;", "-")):
        body = body.replace(a, b)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in body.splitlines()]
    # drop navigation-like fragments: very short lines without sentence punctuation
    return "\n".join(ln for ln in lines if len(ln) > 60 or re.search(r"[.!?:]$", ln))


def _pages(path: Path) -> list[tuple[int | None, str]]:
    """(page number or None, text) pieces of a document."""
    suf = path.suffix.lower()
    if suf == ".pdf":
        from pypdf import PdfReader
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(str(path)).pages)]
    text = path.read_text(encoding="utf-8", errors="ignore")
    if suf in (".html", ".htm"):
        text = _html_text(text)
    return [(None, text)]


def _sentences(text: str) -> list[str]:
    text = re.sub(r"-\n(?=[a-z])", "", text)          # re-join hyphenated line breaks from PDFs
    text = re.sub(r"\s+", " ", text).strip()
    parts = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", text) if s]
    out: list[str] = []
    for s in parts:  # re-join splits after initials and abbreviations ("Octavia E. Butler", "et al. 2020")
        if out and re.search(r"(?:(?<![A-Za-z])[A-Z]|et al|e[.]g|i[.]e|Fig|No|vs)[.]$", out[-1]):
            out[-1] += " " + s
        else:
            out.append(s)
    return out


def _chunks(text: str, size=CHUNK_WORDS, overlap=CHUNK_OVERLAP) -> list[str]:
    """Sentence-aligned chunks of about `size` words with about `overlap` words carried over."""
    out, cur, n = [], [], 0
    for s in _sentences(text):
        w = len(s.split())
        if cur and n + w > size:
            out.append(" ".join(cur))
            keep, kn = [], 0
            for t in reversed(cur):
                if kn >= overlap:
                    break
                keep.insert(0, t)
                kn += len(t.split())
            cur, n = keep, kn
        cur.append(s)
        n += w
    if cur:
        out.append(" ".join(cur))
    return [c for c in out if len(c) > 120]


# ---------------------------------------------------------------- MarsPath's own knowledge


def _internal_docs() -> list[tuple[dict, str]]:
    """Plain-language documents generated from the prepared regions and config, with their sources."""
    docs = []
    for folder in sorted(config.PROCESSED_DIR.glob("*/manifest.json")):
        try:
            m = json.loads(folder.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("is_test_fixture"):
            continue
        rid, rdir = m["region_id"], folder.parent
        lines = [f"MarsPath region '{m.get('name', rid)}' uses these datasets."]
        for k, s in m.get("sources", {}).items():
            if s.get("found"):
                res = s.get("nominal_resolution_m")
                lines.append(f"{s.get('label')}: mission {s.get('mission')}, instrument {s.get('instrument')}"
                             + (f", nominal resolution {res} m" if res else "") + f". Source: {s.get('source_url')}.")
        for n in m.get("notes", []):
            lines.append(f"Processing note: {n}")
        docs.append(({"file": f"marspath:{rid}:datasets", "title": f"MarsPath datasets for {m.get('name', rid)}",
                      "url": f"/api/v1/layers?region_id={rid}", "date": str(m.get("processed_at", ""))[:10],
                      "licence": "MarsPath team (generated from the listed public sources)", "internal": True},
                     "\n".join(lines)))
        ss = rdir / "science_sites.geojson"
        if ss.exists():
            for f in json.loads(ss.read_text(encoding="utf-8")).get("features", []):
                p = f["properties"]
                lo, la = f["geometry"]["coordinates"][:2]
                text = (f"Science site {p.get('name')} at {la:.5f} N, {lo:.5f} E (goal {p.get('goal_id')}). "
                        f"{p.get('observation')} Instruments: {p.get('instrument')}. Date: {p.get('observation_date')}. "
                        f"Why it matters: {p.get('why_it_matters')} Position basis: {p.get('position_basis', '')}. "
                        f"Source: {p.get('source')}.")
                docs.append(({"file": f"marspath:{rid}:site:{p.get('id')}", "title": f"Science site: {p.get('name')}",
                              "url": p.get("source_url"), "date": p.get("observation_date"),
                              "licence": "MarsPath team summary of the cited source", "internal": True}, text))
        val = rdir / "validation.json"
        if val.exists():
            v = json.loads(val.read_text(encoding="utf-8"))
            sm = (v.get("summary") or {}).get("fastest") or {}
            text = (f"Rover benchmark for MarsPath routes. Method: {v.get('method')} Result: over "
                    f"{sm.get('segments')} stretches the planner's route stayed a median "
                    f"{sm.get('median_of_medians_m')} m from Perseverance's real track, versus "
                    f"{sm.get('baseline_median_of_medians_m')} m for a straight line; closer in "
                    f"{sm.get('closer_than_straight_line')} stretches. Caveats: " + " ".join(v.get("caveats", [])))
            docs.append(({"file": f"marspath:{rid}:validation", "title": "MarsPath rover benchmark",
                          "url": f"/api/v1/validation?region_id={rid}", "date": None,
                          "licence": "MarsPath team", "internal": True}, text))
    try:
        eva = config.eva_defaults()
        lines = ["MarsPath EVA (Marswalk) model. Every value is a team assumption, not a NASA requirement."]
        for k, v in eva.items():
            if isinstance(v, dict):
                lines.append(f"{v.get('label', k)}: {v.get('value')} {v.get('unit', '')}. Basis: {v.get('basis', '')}.")
        for r in config.geo_penalties().get("rules", []):
            lines.append(f"Geologic units containing '{r['keyword']}' multiply walking time by {r['multiplier']}: "
                         f"{r['reason']}.")
        docs.append(({"file": "marspath:eva_model", "title": "MarsPath EVA model and assumptions",
                      "url": "/api/v1/eva/defaults", "date": None, "licence": "MarsPath team", "internal": True},
                     "\n".join(lines)))
    except Exception:
        pass
    return docs


# ---------------------------------------------------------------- embeddings


_embedder_cache: dict = {}


def _embedder():
    """Local embedding model, loaded once. Offline it uses the cached copy; returns None if unavailable."""
    if "m" in _embedder_cache:
        return _embedder_cache["m"]
    m = None
    try:
        from fastembed import TextEmbedding
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        try:
            m = TextEmbedding(EMBED_MODEL, cache_dir=str(MODEL_DIR), local_files_only=True)
        except Exception:
            if netutil.is_online():
                m = TextEmbedding(EMBED_MODEL, cache_dir=str(MODEL_DIR))
    except Exception:
        m = None
    _embedder_cache["m"] = m
    return m


def _norm_rows(a: np.ndarray) -> np.ndarray:
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)


# ---------------------------------------------------------------- index


def build_index(docs_dir: Path | None = None, out: Path | None = None, embed: bool = True) -> dict:
    docs_dir = docs_dir or config.DOCS_DIR
    out = out or INDEX
    meta_path = docs_dir / "docs.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else []
    by_file = {m["file"]: m for m in meta if "file" in m}
    chunks, skipped = [], []

    def add(m: dict, pages: list[tuple[int | None, str]]):
        for page, text in pages:
            for c in _chunks(text):
                chunks.append({"doc": m["file"], "title": m.get("title", m["file"]), "url": m.get("url"),
                               "date": m.get("date"), "licence": m.get("licence"), "page": page,
                               "internal": bool(m.get("internal")), "chunk": len(chunks), "text": c,
                               "tokens": _tokens(c)})

    for p in sorted(docs_dir.iterdir()) if docs_dir.exists() else []:
        if p.name in ("docs.json", "docs_sources.json") or p.name.startswith(".") or \
                p.name.lower().startswith("readme") or p.suffix.lower() not in (".txt", ".md", ".html", ".htm", ".pdf"):
            continue
        m = by_file.get(p.name)
        if not m:
            skipped.append(f"{p.name} (no entry in docs.json: title/url/date/licence are required)")
            continue
        try:
            add(m, _pages(p))
        except Exception as e:
            skipped.append(f"{p.name} ({e})")
    for m, text in _internal_docs():
        add(m, [(None, text)])

    df = Counter()
    for c in chunks:
        df.update(set(c["tokens"]))
    emb_info = {"model": None}
    if embed and chunks:
        model = _embedder()
        if model is not None:
            vecs = np.array(list(model.passage_embed([f"{c['title']}. {c['text']}" for c in chunks])), dtype="float32")
            np.save(INDEX_EMB, _norm_rows(vecs).astype("float32"))
            emb_info = {"model": EMBED_MODEL, "dim": int(vecs.shape[1])}
        elif INDEX_EMB.exists():
            INDEX_EMB.unlink()
    idx = {"n": len(chunks), "avgdl": (sum(len(c["tokens"]) for c in chunks) / len(chunks)) if chunks else 0,
           "df": dict(df), "chunks": chunks, "docs": sorted({c["doc"] for c in chunks}), "skipped": skipped,
           "embeddings": emb_info}
    out.write_text(json.dumps(idx), encoding="utf-8")
    _loaded.clear()
    return {"chunks": len(chunks), "documents": len(idx["docs"]),
            "external_documents": sorted({c["doc"] for c in chunks if not c["internal"]}),
            "internal_documents": sum(1 for d in idx["docs"] if d.startswith("marspath:")),
            "embeddings": emb_info, "skipped": skipped}


_loaded: dict = {}


def _index() -> dict | None:
    if not INDEX.exists():
        return None
    mt = INDEX.stat().st_mtime
    if _loaded.get("mtime") != mt:
        _loaded["idx"] = json.loads(INDEX.read_text(encoding="utf-8"))
        _loaded["emb"] = np.load(INDEX_EMB) if INDEX_EMB.exists() else None
        _loaded["mtime"] = mt
    return _loaded["idx"]


# ---------------------------------------------------------------- retrieval


def _bm25(query: str, idx: dict) -> list[tuple[float, int]]:
    q = _tokens(query)
    N, avg, k1, b = idx["n"], idx["avgdl"] or 1, 1.5, 0.75
    out = []
    for i, c in enumerate(idx["chunks"]):
        tf = Counter(c["tokens"])
        dl = len(c["tokens"])
        s = 0.0
        for t in q:
            if t in tf:
                n = idx["df"].get(t, 0)
                s += math.log(1 + (N - n + 0.5) / (n + 0.5)) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / avg))
        if s > 0:
            out.append((s, i))
    out.sort(key=lambda x: -x[0])
    return out


def _dense(query: str, idx: dict) -> list[tuple[float, int]] | None:
    emb = _loaded.get("emb")
    model = _embedder() if emb is not None else None
    if emb is None or model is None or len(emb) != idx["n"]:
        return None
    qv = np.array(list(model.query_embed([query]))[0], dtype="float32")
    qv /= max(float(np.linalg.norm(qv)), 1e-12)
    sims = emb @ qv
    order = np.argsort(-sims)[:50]
    return [(float(sims[i]), int(i)) for i in order]


def search(query: str, k: int = 5, idx: dict | None = None, mode: str = "hybrid") -> list[dict]:
    """mode: 'hybrid' (default), 'bm25' or 'dense'."""
    idx = idx or _index()
    if not idx or not idx["n"]:
        return []
    bm = _bm25(query, idx)[:50]
    de = _dense(query, idx) if mode in ("hybrid", "dense") else None
    bm_score = {i: s for s, i in bm}
    de_score = {i: s for s, i in (de or [])}
    if mode == "bm25" or de is None:
        ranked = [i for _, i in bm]
        used = "bm25"
    elif mode == "dense":
        ranked = [i for _, i in de]
        used = "dense"
    else:
        rrf: dict[int, float] = {}
        for lst in (bm, de):
            for r, (_, i) in enumerate(lst):
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
        ranked = sorted(rrf, key=lambda i: -rrf[i])
        used = "hybrid"
    qt = set(_tokens(query))
    out = []
    for i in ranked[:k]:
        c = idx["chunks"][i]
        cov = len(qt & set(c["tokens"])) / len(qt) if qt else 0.0
        out.append({**{k2: v for k2, v in c.items() if k2 != "tokens"},
                    "bm25": round(bm_score.get(i, 0.0), 3), "cosine": round(de_score.get(i, 0.0), 3),
                    "query_coverage": round(cov, 2), "retrieval": used})
    return out


def _relevant(h: dict) -> bool:
    """Semantic gate when embeddings exist (keyword overlap alone lets off-topic questions through);
    without embeddings, at least half of the question's key words must appear in the passage."""
    if h.get("retrieval") in ("hybrid", "dense"):
        return h["cosine"] >= COS_FOUND
    return h["bm25"] > 0 and h.get("query_coverage", 0) >= 0.5


# ---------------------------------------------------------------- answering


def _point_source(region, lon: float, lat: float) -> dict | None:
    """MarsPath's own readout for a point, as a citable (model-derived) source."""
    try:
        from .eva import EvaParams
        from .point_info import point_info
        if region is None or not region.grid.contains(lon, lat):
            return None
        pi = point_info(region, lon, lat, EvaParams.defaults())
        t, geo = pi["terrain"], pi.get("geology") or {}
        site = pi.get("nearest_science_site") or {}
        rover = pi.get("nearest_rover_stop") or {}
        text = (f"MarsPath data for the point {lat:.5f} N, {lon:.5f} E: elevation {t['elevation_m']} m, "
                f"slope {t['slope_deg']} deg, roughness {t['roughness_m']} m; geologic unit {geo.get('unit', 'unmapped')}; "
                f"walkable under the default EVA limits: {pi['walkable']}"
                + (f" ({'; '.join(pi['not_walkable_because'])})" if pi["not_walkable_because"] else "")
                + f". Nearest science site: {site.get('name')} at {site.get('distance_m')} m. "
                f"Nearest Perseverance stop: sol {rover.get('sol')} at {rover.get('distance_m')} m.")
        return {"title": "MarsPath data at the selected point (model-derived)", "url":
                f"/api/v1/point-info?region_id={region.region_id}&lon={lon}&lat={lat}", "date": None,
                "doc": "marspath:point", "page": None, "text": text, "internal": True, "bm25": 0.0, "cosine": 1.0,
                "retrieval": "location"}
    except Exception:
        return None


def _cite(i: int, h: dict) -> dict:
    return {"n": i + 1, "title": h["title"], "url": h["url"], "date": h.get("date"), "doc": h["doc"],
            "page": h.get("page"), "internal": bool(h.get("internal")), "licence": h.get("licence"),
            "retrieval": h.get("retrieval"), "bm25": h.get("bm25"), "cosine": h.get("cosine"),
            "snippet": h["text"][:420] + ("..." if len(h["text"]) > 420 else "")}


def _extractive(q: str, hits: list[dict]) -> str:
    qt = set(_tokens(q))
    picked = []
    for n, h in enumerate(hits[:3], start=1):
        sents = _sentences(h["text"])
        if not sents:
            continue
        best = max(sents, key=lambda s: (len(qt & set(_tokens(s))), -abs(len(s) - 160)))
        if len(qt & set(_tokens(best))) == 0 and n > 1:
            continue
        picked.append(f"{best.strip()} [{n}]")
    return " ".join(picked)[:900]


def ask(question: str, region_name: str | None = None, lon: float | None = None, lat: float | None = None,
        region=None, k: int = 5) -> dict:
    q = question.strip()
    if not q:
        raise ValueError("empty question")
    idx = _index()
    if not idx or not idx["n"]:
        return {"found": False, "mode": "none", "answer": "The document library is empty. Run "
                "backend/scripts/fetch_docs.py (online) or build_assistant_index.py.", "citations": []}
    hits = [h for h in search(q, k=k, idx=idx) if _relevant(h)]
    point = _point_source(region, lon, lat) if (lon is not None and lat is not None) else None
    if point:
        hits.insert(0, point)  # a question asked at a point is answered from that point's data first
    if not hits:
        return {"found": False, "mode": "retrieval", "answer": "Not found in the loaded documents.", "citations": [],
                "retrieval": "hybrid" if _loaded.get("emb") is not None else "bm25"}
    cites = [_cite(i, h) for i, h in enumerate(hits)]
    note = ""
    if config.ANTHROPIC_API_KEY and netutil.is_online():
        try:
            ctx = "\n\n".join(f"[{i+1}] ({h['title']}{', page ' + str(h['page']) if h.get('page') else ''}"
                              f"{'; MarsPath data' if h.get('internal') else ''})\n{h['text']}" for i, h in enumerate(hits))
            where = (f" The user is looking at {region_name or 'the map'}, lon {lon:.4f} E, lat {lat:.4f} N."
                     if lon is not None and lat is not None else (f" Region: {region_name}." if region_name else ""))
            import httpx
            r = httpx.post("https://api.anthropic.com/v1/messages", timeout=45,
                           headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                                    "content-type": "application/json"},
                           json={"model": config.LLM_MODEL, "max_tokens": 450, "system": GUARDRAIL,
                                 "messages": [{"role": "user", "content": f"Sources:\n{ctx}\n\nQuestion: {q}{where}"}]})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
            if "NOT_IN_DOCUMENTS" in text:
                return {"found": False, "mode": "llm", "answer": "Not found in the loaded documents.", "citations": cites}
            used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})
            bad = [n for n in used if not 1 <= n <= len(hits)]
            text = re.sub(r"\[(\d+)\]", lambda m: m.group(0) if 1 <= int(m.group(1)) <= len(hits) else "", text)
            return {"found": True, "mode": "llm", "model": config.LLM_MODEL, "answer": text,
                    "citations": cites, "cited": [n for n in used if n not in bad],
                    "citation_check": "ok" if not bad and used else ("no citations in answer" if not used
                                                                     else f"removed invalid citations {bad}")}
        except Exception as e:
            note = f" (LLM unavailable: {str(e).splitlines()[0][:120]})"
    return {"found": True, "mode": "extractive", "answer": _extractive(q, hits) or hits[0]["text"][:500] + " [1]",
            "note": "Extractive answer: the most relevant sentences from the sources, quoted, not a generated summary."
                    + note, "citations": cites}
