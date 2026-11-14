"""Decision metrics on the dev set (B4): bid-or-skip F1, scam precision/recall, price inside the fair band,
injection detection, plus p50/p95 latency and tokens/USD per job analysed.

    python -m evals.runners.decision_eval --per-persona 30            # LLM + rules (open profile)
    python -m evals.runners.decision_eval --offline --per-persona 200 # rules/heuristics only (ablation)
Runs the real bid graph in analysis_only mode (stops after pricing; nothing is drafted or sent).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from evals.harness import PERSONAS, load_dev, mean, pct, run_job, setup_inprocess, stratified, write


def f1(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "tp": tp, "fp": fp, "fn": fn}


def metrics(rows: list[dict]) -> dict:
    bid = f1(sum(r["pred_bid"] and r["gold_bid"] for r in rows), sum(r["pred_bid"] and not r["gold_bid"] for r in rows),
             sum(not r["pred_bid"] and r["gold_bid"] for r in rows))
    scam = f1(sum(r["pred_scam"] and r["gold_scam"] for r in rows), sum(r["pred_scam"] and not r["gold_scam"] for r in rows),
              sum(not r["pred_scam"] and r["gold_scam"] for r in rows))
    priced = [r for r in rows if r["price"] is not None and r["gold_bid"]]
    inj = [r for r in rows if r["gold_injection"]]
    return {"n": len(rows), "bid_skip": bid, "accuracy": round(mean([float(r["pred_bid"] == r["gold_bid"]) for r in rows]) or 0, 3),
            "scam": scam,
            "price_in_fair_band": round(mean([float(r["in_band"]) for r in priced]) or 0, 3) if priced else None,
            "n_priced": len(priced),
            "injection_detected_rate": round(mean([float(r["pred_injection"]) for r in inj]) or 0, 3) if inj else None,
            "latency_p50_s": pct([r["latency_s"] for r in rows], 0.5), "latency_p95_s": pct([r["latency_s"] for r in rows], 0.95),
            "tokens_per_job": mean([r["tokens"] for r in rows]), "usd_per_job": mean([r["usd"] for r in rows])}


async def main_async(per: int, offline: bool, out: str) -> None:
    if offline:
        os.environ["LLM_OFFLINE"] = "1"
    setup_inprocess()
    rows = []
    for persona in PERSONAS:
        jobs = stratified(load_dev(persona), per, seed=3)
        for i, j in enumerate(jobs):
            g = j["gold"]
            try:
                r = await run_job(persona, j, analysis_only=True, user="dec")
            except Exception as e:  # noqa: BLE001
                print("FAILED", j["job_id"], e)
                continue
            st = r["state"]
            price = (st.get("price") or {}).get("amount")
            band = g["fair_price_band"]
            ptype = (st.get("price") or {}).get("bid_type")
            in_band = None
            if price is not None:
                in_band = (band[0] <= price <= band[1]) if ptype == "fixed" else (
                    band[0] / max(1, g["est_hours"]) * 0.8 <= price <= band[1] / max(1, g["est_hours"]) * 1.2)
            rows.append({"persona": persona, "job_id": j["job_id"], "kind": g["kind"], "gold_bid": g["bid"], "gold_scam": g["scam"],
                         "gold_injection": g["injection"], "pred_action": (st.get("decision") or {}).get("action"),
                         "pred_bid": (st.get("decision") or {}).get("action") == "bid",
                         "pred_scam": bool((st.get("risk") or {}).get("scam")),
                         "pred_injection": bool((st.get("risk") or {}).get("injection_detected")),
                         "fit": (st.get("fit") or {}).get("score"), "risk": (st.get("risk") or {}).get("score"),
                         "flags": (st.get("risk") or {}).get("flags"), "price": price, "price_type": ptype,
                         "fair_band": band, "in_band": in_band, "status": st.get("status"),
                         "reasons": (st.get("decision") or {}).get("reasons"), "latency_s": r["latency_s"],
                         "tokens": r["tokens"], "usd": r["usd"]})
            print(f"{persona} {i + 1}/{len(jobs)} {j['job_id']} gold={g['bid']} pred={rows[-1]['pred_action']} "
                  f"lat={r['latency_s']}s", flush=True)
    res = {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "per_persona": per,
                    "mode": "rules+heuristics (offline)" if offline else "llm+rules (open profile)"},
           "overall": metrics(rows), "by_persona": {p: metrics([r for r in rows if r["persona"] == p]) for p in PERSONAS},
           "by_kind": {k: metrics([r for r in rows if r["kind"] == k]) for k in sorted({r["kind"] for r in rows})},
           "rows": rows}
    write(out, res)
    print({k: res["overall"][k] for k in ("bid_skip", "scam", "price_in_fair_band", "latency_p95_s", "usd_per_job")})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=30)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    asyncio.run(main_async(a.per_persona, a.offline, a.out or ("decision_offline" if a.offline else "decision")))


if __name__ == "__main__":
    main()
