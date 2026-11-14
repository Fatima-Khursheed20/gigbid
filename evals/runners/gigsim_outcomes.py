"""End-to-end proposal evaluation on a FIXED job set (B4/B5): for each retrieval variant, run the full bid graph,
auto-approve, submit to the in-process GigSim and read the simulated client's decision.

Records per proposal: unsupported claims before/after verification, Critic rounds, LLM-judge rubric score,
GigSim reply / interview / hire, latency, tokens and USD. Drafts are saved for judge calibration and the
blind human panel.

    python -m evals.runners.gigsim_outcomes --variants v0_naive,v4_outcome --per-persona 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from pydantic import BaseModel

from common import llm
from common.config import load_config, prompt
from evals.harness import PERSONAS, load_dev, mean, pct, run_job, setup_inprocess, stratified, write


class Judge(BaseModel):
    relevance: int
    evidence: int
    personalisation: int
    clarity: int
    professionalism: int
    overall: int
    rationale: str = ""


async def judge(job: dict, text: str) -> dict | None:
    try:
        j = await llm.structured("judge", prompt("judge"), f"JOB POST:\n{job['title']}\n{job['description'][:1500]}\n\n"
                                 f"PROPOSAL:\n{text}", Judge, max_tokens=400, temperature=0.0)
        return j.model_dump()
    except Exception as e:  # noqa: BLE001
        print("judge failed", e)
        return None


def fixed_jobs(per: int) -> dict[str, list[dict]]:
    out = {}
    for p in PERSONAS:
        bid = [r for r in load_dev(p) if r["gold"]["bid"] and r["gold"]["kind"] in ("fit", "vague")]
        out[p] = stratified(bid, per, seed=5)
    return out


async def run_variant(variant: str, jobs: dict[str, list[dict]]) -> list[dict]:
    import gigsim.app as gs

    load_config()["rag"]["variant"] = variant
    rows = []
    for persona, js in jobs.items():
        for j in js:
            t0 = time.time()
            try:
                r = await run_job(persona, j, approve=True, user=f"out-{variant}")
            except Exception as e:  # noqa: BLE001
                print("FAILED", variant, j["job_id"], e)
                continue
            st = r["state"]
            draft = st.get("draft") or {}
            sub = r.get("submit") or {}
            outcome = None
            if sub.get("proposal_id"):
                o = gs.STORE.q("select outcome from proposals where id=?", (sub["proposal_id"],))
                outcome = json.loads(o[0]["outcome"]) if o and o[0]["outcome"] else None
            text = (r.get("state_after") or st).get("draft", {}).get("cover_letter", "")
            jscore = await judge(j, text) if text else None
            ver = st.get("verification") or {}
            rows.append({"variant": variant, "persona": persona, "job_id": j["job_id"], "status": st.get("status"),
                         "submitted": bool(sub.get("proposal_id")), "replied": bool(outcome and outcome.get("replied")),
                         "interview": bool(outcome and outcome.get("interview")), "hired": bool(outcome and outcome.get("hired")),
                         "p_reply": outcome.get("p_reply") if outcome else None,
                         "client_features": outcome.get("features") if outcome else None,
                         "unsupported_before": (ver.get("before") or {}).get("unsupported"),
                         "unsupported_after": (ver.get("after") or {}).get("unsupported"),
                         "claims": (ver.get("before") or {}).get("claims"), "partly_before": ver.get("partly_before"),
                         "critic_rounds": len(st.get("critiques", [])), "words": draft.get("word_count"),
                         "judge": jscore, "latency_s": r["latency_s"], "tokens": r["tokens"], "usd": r["usd"],
                         "wall_s": round(time.time() - t0, 1), "text": text,
                         "evidence_projects": sorted({e.get("project_id") for e in st.get("evidence", []) if e.get("project_id")}),
                         "gold_projects": [g["project_id"] for g in j["gold"]["evidence"]]})
            print(f"{variant} {persona} {j['job_id']} status={st.get('status')} replied={rows[-1]['replied']} "
                  f"unsup={rows[-1]['unsupported_before']}->{rows[-1]['unsupported_after']} judge="
                  f"{(jscore or {}).get('overall')} lat={r['latency_s']}s", flush=True)
    return rows


def summary(rows: list[dict]) -> dict:
    sub = [r for r in rows if r["submitted"]]
    return {"n": len(rows), "submitted": len(sub),
            "reply_rate": round(mean([float(r["replied"]) for r in sub]) or 0, 3) if sub else None,
            "hire_rate": round(mean([float(r["hired"]) for r in sub]) or 0, 3) if sub else None,
            "mean_p_reply": mean([r["p_reply"] for r in sub]),
            "unsupported_per_proposal_before": mean([r["unsupported_before"] for r in rows]),
            "unsupported_per_proposal_after": mean([r["unsupported_after"] for r in rows]),
            "claims_per_proposal": mean([r["claims"] for r in rows]),
            "judge_overall": mean([r["judge"]["overall"] for r in rows if r["judge"]]),
            "evidence_recall": mean([len(set(r["evidence_projects"]) & set(r["gold_projects"])) / max(1, len(r["gold_projects"]))
                                     for r in rows]),
            "latency_p50_s": pct([r["latency_s"] for r in rows], 0.5), "latency_p95_s": pct([r["latency_s"] for r in rows], 0.95),
            "tokens_per_proposal": mean([r["tokens"] for r in rows]), "usd_per_proposal": mean([r["usd"] for r in rows])}


async def main_async(variants: list[str], per: int, out: str) -> None:
    setup_inprocess()
    jobs = fixed_jobs(per)
    rows = []
    for v in variants:
        rows += await run_variant(v, jobs)
        write(out, {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "per_persona": per, "variants": variants,
                             "client_model": "gigsim/client_model.py (rule-based, seeded)"},
                    "by_variant": {x: summary([r for r in rows if r["variant"] == x]) for x in variants},
                    "by_variant_persona": {f"{x}|{p}": summary([r for r in rows if r["variant"] == x and r["persona"] == p])
                                           for x in variants for p in PERSONAS},
                    "rows": rows})
    print(json.dumps({v: summary([r for r in rows if r["variant"] == v]) for v in variants}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="v0_naive,v4_outcome")
    ap.add_argument("--per-persona", type=int, default=5)
    ap.add_argument("--out", default="gigsim_outcomes")
    a = ap.parse_args()
    asyncio.run(main_async(a.variants.split(","), a.per_persona, a.out))


if __name__ == "__main__":
    main()
