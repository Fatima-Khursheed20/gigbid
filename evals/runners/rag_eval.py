"""Retrieval evaluation of every RAG variant on the dev set, per persona and per job type (B4/B5).

    python -m evals.runners.rag_eval                    # all variants, all personas
    python -m evals.runners.rag_eval --variants v0_naive,v3_rerank --limit 30
    python -m evals.runners.rag_eval --ablate v4_outcome  # drop one component at a time from a pipeline

Writes evals/results/rag_retrieval.json (+ .csv). Requirements for V1+ come from the heuristic extractor
(offline) unless --llm-requirements is given and the analyst cache is available. HyDE (V7) needs LLM text.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import statistics
import time
from collections import defaultdict

from common.settings import ROOT
from rag.corpus import Corpus
from rag.metrics import mrr, ndcg_at_k, project_ranking, recall_at_k
from rag.pipeline import Query, heuristic_requirements
from rag.retriever import VARIANTS, make

PERSONAS = ["ai_ml", "fullstack", "data_analyst"]
RESULTS = ROOT / "evals" / "results"


def load_dev(persona: str, limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in (ROOT / "evals" / "datasets" / f"dev_{persona}.jsonl").open(encoding="utf-8")]
    return rows[:limit] if limit else rows


def job_text(j: dict) -> str:
    return f"{j['title']}\n\n{j['description']}"


def _mean(xs: list[float]) -> float:
    xs = [x for x in xs if not (isinstance(x, float) and math.isnan(x))]
    return round(statistics.mean(xs), 4) if xs else float("nan")


async def _hyde_for(jobs: list[dict]) -> dict[str, str]:
    from rag.variants.v7_hyde import hyde_text

    out = {}
    sem = asyncio.Semaphore(4)

    async def one(j):
        async with sem:
            try:
                out[j["job_id"]] = await hyde_text(job_text(j))
            except Exception as e:  # noqa: BLE001
                print("hyde failed", j["job_id"], str(e)[:80])

    await asyncio.gather(*(one(j) for j in jobs))
    return out


def evaluate(variants: list, personas: list[str], limit: int | None, requirements: dict[str, list[str]] | None = None,
             hyde: dict[str, str] | None = None) -> dict:
    rows = []
    for persona in personas:
        corpus = Corpus(ROOT / "data" / "personas" / persona, persona)
        jobs = load_dev(persona, limit)
        for v in variants:
            name = v if isinstance(v, str) else v.name
            settings = VARIANTS[v] if isinstance(v, str) else v
            if settings.query == "hyde" and not hyde:
                continue
            retr = make(corpus, settings)
            for j in jobs:
                gold = {g["project_id"]: g["grade"] for g in j["gold"]["evidence"]}
                reqs = (requirements or {}).get(j["job_id"]) or heuristic_requirements(job_text(j))
                q = Query(job_text=job_text(j), requirements=reqs, hyde_text=(hyde or {}).get(j["job_id"]))
                t0 = time.perf_counter()
                if settings.crag:
                    res = retr.run(q)
                    ev = [e for m in res["matrix"] for e in m["evidence"]]
                    refuse = res["refuse"]
                else:
                    ev = retr.retrieve(q, k=5)
                    refuse = None
                dt = time.perf_counter() - t0
                ranked = project_ranking(ev)
                rows.append({"variant": name, "persona": persona, "job_id": j["job_id"], "kind": j["gold"]["kind"],
                             "n_req": len(j["gold"]["required_skills"]), "bid": j["gold"]["bid"],
                             "has_gold": bool(gold), "recall@5": recall_at_k(ranked, gold, 5), "mrr": mrr(ranked, gold),
                             "ndcg@10": ndcg_at_k(ranked, gold, 10), "latency_s": round(dt, 4), "refuse": refuse,
                             "top5": ranked[:5]})
            print(f"{persona:13s} {name:28s} done ({len(jobs)} jobs)")
    return summarise(rows)


def summarise(rows: list[dict]) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[(r["variant"], "ALL")].append(r)
        by[(r["variant"], r["persona"])].append(r)
        by[(r["variant"], f"kind={r['kind']}")].append(r)
        if r["n_req"] >= 4:
            by[(r["variant"], "n_req>=4")].append(r)
    table = []
    for (v, slice_), rs in sorted(by.items()):
        g = [r for r in rs if r["has_gold"]]
        lat = sorted(r["latency_s"] for r in rs)
        entry = {"variant": v, "slice": slice_, "n": len(g), "recall@5": _mean([r["recall@5"] for r in g]),
                 "mrr": _mean([r["mrr"] for r in g]), "ndcg@10": _mean([r["ndcg@10"] for r in g]),
                 "p50_latency_s": round(lat[len(lat) // 2], 4) if lat else None,
                 "p95_latency_s": round(lat[int(len(lat) * 0.95) - 1], 4) if lat else None}
        ref = [r for r in rs if r["refuse"] is not None]
        if ref:
            skip = [r for r in ref if r["kind"] in ("ood", "partial")]
            fit = [r for r in ref if r["kind"] in ("fit", "vague")]
            entry["refusal_rate_on_should_skip"] = _mean([float(r["refuse"]) for r in skip])
            entry["refusal_rate_on_fit"] = _mean([float(r["refuse"]) for r in fit])
        table.append(entry)
    return {"table": table, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--personas", default=",".join(PERSONAS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ablate", default=None, help="variant whose components are removed one at a time")
    ap.add_argument("--hyde", action="store_true", help="generate HyDE texts with the LLM (needs API key)")
    ap.add_argument("--out", default="rag_retrieval")
    a = ap.parse_args()
    personas = a.personas.split(",")
    hyde = None
    if a.hyde:
        jobs = [j for p in personas for j in load_dev(p, a.limit)]
        hyde = asyncio.run(_hyde_for(jobs))
    if a.ablate:
        base = VARIANTS[a.ablate]
        comps = [c for c in ("query", "hybrid", "rerank", "outcome", "multivector", "contextual") if
                 (getattr(base, c) not in (False, "whole"))]
        variants = [base] + [base.without(c) for c in comps]
    else:
        variants = [v for v in a.variants.split(",") if v]
    res = evaluate(variants, personas, a.limit, hyde=hyde)
    RESULTS.mkdir(parents=True, exist_ok=True)
    meta = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "limit": a.limit, "personas": personas,
            "embeddings": __import__("common.config", fromlist=["cfg"]).cfg("models", "embeddings"),
            "reranker": __import__("common.config", fromlist=["cfg"]).cfg("models", "reranker"),
            "requirements_source": "heuristic", "hyde": bool(hyde)}
    (RESULTS / f"{a.out}.json").write_text(json.dumps({"meta": meta, **res}, indent=1), encoding="utf-8")
    with (RESULTS / f"{a.out}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res["table"][0].keys()) + ["refusal_rate_on_should_skip", "refusal_rate_on_fit"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(res["table"])
    for r in res["table"]:
        if r["slice"] == "ALL":
            print(f"{r['variant']:32s} R@5={r['recall@5']:.3f} MRR={r['mrr']:.3f} nDCG@10={r['ndcg@10']:.3f} "
                  f"p95={r['p95_latency_s']}s" + (f" refuse(skip)={r.get('refusal_rate_on_should_skip')}"
                                                   f" refuse(fit)={r.get('refusal_rate_on_fit')}" if 'refusal_rate_on_fit' in r else ""))


if __name__ == "__main__":
    main()
