"""Retrieval evaluation for the assistant: does the right document come back in the top k?

Each question lists the document(s) that contain the answer. Reports hit@1 and hit@3 for BM25
only, dense only and the hybrid used in production. Run after building the index:

    python backend/scripts/eval_assistant.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import assistant  # noqa: E402

EVAL = [
    ("Where did Perseverance detect the most abundant organic molecules?", ["jpl_wildcat_ridge_organics.html", "marspath:jezero:site:site-06"]),
    ("Which rock contains organics correlated with sulfate minerals?", ["jpl_wildcat_ridge_organics.html", "marspath:jezero:site:site-06"]),
    ("What were the first two rock cores collected by the rover?", ["nasa_first_rock_samples.html", "marspath:jezero:site:site-02", "nasa_m2020_rock_samples.html"]),
    ("Where were the sample tubes left on the surface for later return?", ["nasa_sample_depot.html", "marspath:jezero:site:site-08"]),
    ("What kind of rock is in the Seitah formation at Brac?", ["marspath:jezero:site:site-03", "seitah_olivine_clay_carbonate.pdf"]),
    ("How much radiation dose per day did Curiosity measure on the surface?", ["swri_rad_surface_radiation.html"]),
    ("What is the resolution of the HiRISE terrain model used for routing?", ["marspath:jezero:datasets", "usgs_m2020_trn_hirise_dtm.html"]),
    ("What steepest slope may a suited walker take in MarsPath?", ["marspath:eva_model"]),
    ("Why does walking over wind-blown sand take longer?", ["marspath:eva_model"]),
    ("How well do MarsPath routes match the rover's real drives?", ["marspath:jezero:validation"]),
    ("Where are carbonates found along the margin of Jezero crater?", ["zastrow_glotch_2021_jezero_carbonates.html", "brown2020_jezero_olivine_carbonate.pdf", "marspath:jezero:site:site-10"]),
    ("How cold does the air get at Jezero during the day and night?", ["meda_2023_natgeo_jezero_weather.html"]),
    ("What geologic units make up the floor of Jezero crater?", ["sim3464_pamphlet.pdf", "stack2020_jezero_photogeologic_map.html"]),
    ("How long would a crew stay on the surface of Mars in the reference mission?", ["nasa_dra5_human_mars.pdf"]),
    ("Who is the landing site named after?", ["jpl_octavia_butler_landing.html", "marspath:jezero:site:site-01"]),
]


def main():
    idx = assistant._index()
    if not idx:
        print("No index: run fetch_docs.py first")
        return 1
    report = {}
    for mode in ("bm25", "dense", "hybrid"):
        h1 = h3 = 0
        for q, gold in EVAL:
            docs = [h["doc"] for h in assistant.search(q, k=3, idx=idx, mode=mode)]
            h1 += bool(docs[:1] and docs[0] in gold)
            h3 += any(d in gold for d in docs)
        report[mode] = {"hit@1": f"{h1}/{len(EVAL)}", "hit@3": f"{h3}/{len(EVAL)}"}
    print(json.dumps(report, indent=2))
    out = assistant.config.CACHE_DIR / "assistant_eval.json"
    out.write_text(json.dumps({"questions": len(EVAL), "results": report}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
