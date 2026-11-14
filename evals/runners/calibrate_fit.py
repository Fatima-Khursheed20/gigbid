"""Calibrate the evidence-grading threshold (rag.crag_min_score) and the fit thresholds (thresholds.bid_min_fit /
watch_min_fit) on DEV jobs. Offline: cross-encoder scores only, no LLM. The chosen values are then frozen in
agent/config.yaml and the held-out set is used once for the final numbers.

    python -m evals.runners.calibrate_fit --per-persona 40
"""

from __future__ import annotations

import argparse
import itertools
import time

from evals.harness import PERSONAS, load_dev, stratified, write
from mcp_servers.portfolio.tools import STORE
from rag.index.embeddings import get_reranker
from rag.pipeline import Pipeline, Query, heuristic_requirements
from rag.retriever import settings_for

KINDS = ("fit", "vague", "partial", "ood", "injection")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=40)
    ap.add_argument("--variant", default="v4_outcome")
    a = ap.parse_args()
    rr = get_reranker()
    rows = []
    for p in PERSONAS:
        corpus = STORE.corpus(p)
        s = settings_for(a.variant)
        pipe = Pipeline(corpus, type(s)(**{**s.__dict__, "crag": False, "query": "whole"}))
        jobs = stratified([r for r in load_dev(p) if r["gold"]["kind"] in KINDS], a.per_persona, seed=13)
        for j in jobs:
            reqs = heuristic_requirements(f"{j['title']}\n\n{j['description']}")[:8]
            best = []
            for q in reqs:
                ev = pipe.retrieve(Query(job_text=q), k=5)[:5]
                best.append(max(rr.score(q[:500], [e["text"] for e in ev])) if ev else -99.0)
            rows.append({"persona": p, "job_id": j["job_id"], "kind": j["gold"]["kind"], "gold_bid": j["gold"]["bid"],
                         "best": best})
        print(p, "scored", flush=True)
    grid = []
    for t, bid_min, weak_w in itertools.product([-6, -5, -4, -3, -2, -1, 0], [0.35, 0.4, 0.45, 0.5, 0.55], [0.35, 0.5]):
        tp = fp = fn = tn = 0
        for r in rows:
            w = [1.0 if b >= t else (weak_w if b > t - 3 else 0.0) for b in r["best"]]
            fit = sum(w) / max(1, len(w))
            pred = fit >= bid_min
            tp += pred and r["gold_bid"]
            fp += pred and not r["gold_bid"]
            fn += (not pred) and r["gold_bid"]
            tn += (not pred) and not r["gold_bid"]
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        grid.append({"crag_min_score": t, "bid_min_fit": bid_min, "weak_weight": weak_w, "precision": round(prec, 3),
                     "recall": round(rec, 3), "f1": round(f1, 3)})
    grid.sort(key=lambda g: (-g["f1"], -g["precision"]))
    write("fit_calibration", {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "variant": a.variant,
                                       "per_persona": a.per_persona, "kinds": KINDS, "split": "dev"},
                              "best": grid[0], "top10": grid[:10], "current": next(
                                  g for g in grid if g["crag_min_score"] == 0 and g["bid_min_fit"] == 0.55 and g["weak_weight"] == 0.35),
                              "rows": rows})
    print("current", next(g for g in grid if g["crag_min_score"] == 0 and g["bid_min_fit"] == 0.55 and g["weak_weight"] == 0.35))
    for g in grid[:5]:
        print(g)


if __name__ == "__main__":
    main()
