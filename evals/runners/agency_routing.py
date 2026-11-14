"""X1 evaluation: does GigBid route each job to the right team member?

Gold: every dev job was generated for one persona (gold.persona). On jobs that persona should bid on, the
correct member is that persona. Baseline: route by the job's marketplace category (ai_ml/web/data).

    python -m evals.runners.agency_routing --per-persona 30
"""

from __future__ import annotations

import argparse
import asyncio
import time

from agent.agency import route
from evals.harness import PERSONAS, load_dev, setup_inprocess, stratified, write

CAT = {"ai_ml": "ai_ml", "web": "fullstack", "data": "data_analyst"}


async def main_async(per: int) -> None:
    setup_inprocess()
    rows = []
    for p in PERSONAS:
        jobs = stratified([r for r in load_dev(p) if r["gold"]["bid"]], per, seed=9)
        for j in jobs:
            t0 = time.perf_counter()
            r = await route(j, PERSONAS, mode="inprocess")
            rows.append({"job_id": j["job_id"], "gold": p, "routed": r["member"], "scores": r["scores"],
                         "baseline": CAT.get(j["category"]), "confident": r["confident"],
                         "latency_s": round(time.perf_counter() - t0, 2)})
            print(j["job_id"], p, "->", r["member"], r["scores"], flush=True)
    acc = sum(r["routed"] == r["gold"] for r in rows) / len(rows)
    base = sum(r["baseline"] == r["gold"] for r in rows) / len(rows)
    conf = [r for r in rows if r["confident"]]
    res = {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "per_persona": per,
                    "note": "category baseline is near-perfect by construction on this synthetic set; the useful "
                            "comparison is on jobs whose category is ambiguous (vague posts)"},
           "n": len(rows), "routing_accuracy": round(acc, 3), "category_baseline_accuracy": round(base, 3),
           "confident_share": round(len(conf) / len(rows), 3),
           "accuracy_when_confident": round(sum(r["routed"] == r["gold"] for r in conf) / max(1, len(conf)), 3),
           "by_persona": {p: round(sum(r["routed"] == r["gold"] for r in rows if r["gold"] == p) /
                                   max(1, sum(r["gold"] == p for r in rows)), 3) for p in PERSONAS},
           "rows": rows}
    write("agency_routing", res)
    print({k: res[k] for k in ("n", "routing_accuracy", "category_baseline_accuracy", "accuracy_when_confident")})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=30)
    asyncio.run(main_async(ap.parse_args().per_persona))


if __name__ == "__main__":
    main()
