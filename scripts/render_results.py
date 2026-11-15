"""Render the README results tables from evals/results/*.json (every number in README traces to a file).

    python -m scripts.render_results     # rewrites the blocks between <!-- results:FILE --> markers
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"


def load(name: str) -> dict | None:
    p = RES / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def f(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def rag_table() -> str:
    d = load("rag_retrieval.json")
    rows = [r for r in d["table"] if r["slice"] == "ALL"]
    out = ["| Variant | Recall@5 | MRR | nDCG@10 | p95 retrieval latency (s) |", "|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['variant']} | {f(r['recall@5'])} | {f(r['mrr'])} | {f(r['ndcg@10'])} | {f(r['p95_latency_s'], 2)} |")
    n = rows[0]["n"]
    return "\n".join(out) + f"\n\n*{n} dev jobs with gold evidence (60 stratified per persona), `evals/results/rag_retrieval.json`.*"


def b5_table() -> str:
    out = ["| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal (before → after verification) | Judge score (1-5) | GigSim reply rate | p95 latency (s) | Cost / proposal (USD, list price) |",
           "|---|---|---|---|---|---|---|---|"]
    rag = {r["variant"]: r for r in load("rag_retrieval.json")["table"] if r["slice"] == "ALL"}
    for v, fn in [("v0_naive", "gigsim_outcomes.json"), ("v4_outcome", "gigsim_outcomes_v4.json"),
                  ("v5_multivector", "gigsim_outcomes_v5.json")]:
        d = load(fn)
        if not d or v not in d["by_variant"]:
            continue
        s = d["by_variant"][v]
        out.append(f"| {v}{' (shipped)' if v == 'v5_multivector' else ''} | {f(rag[v]['recall@5'])} | {f(rag[v]['ndcg@10'])} | "
                   f"{f(s['unsupported_per_proposal_before'], 2)} → {f(s['unsupported_per_proposal_after'], 2)} | "
                   f"{f(s['judge_overall'], 2)} | {f(s['reply_rate'], 2)} (n={s['submitted']}) | {f(s['latency_p95_s'], 0)} | "
                   f"{f(s['usd_per_proposal'], 4)} |")
    return "\n".join(out) + "\n\n*Retrieval columns: `rag_retrieval.json`; proposal columns: `gigsim_outcomes*.json` (5 bid-worthy jobs per persona, same jobs for every variant).*"


def decision_table() -> str:
    out = ["| Mode | Jobs | Bid/skip F1 | Precision | Recall | Scam precision | Scam recall | Price in fair band | Injection flagged | p95 s / job | USD / job |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, label in [("decision_offline.json", "rules only, pre-calibration"), ("decision.json", "LLM + rules, pre-calibration"),
                        ("decision_v2.json", "LLM + rules, calibrated (shipped)"), ("heldout_decision.json", "held-out, quota-degraded run"), ("heldout_decision_v2.json", "held-out, full models (re-run)")]:
        d = load(name)
        if not d:
            continue
        o = d["overall"]
        out.append(f"| {label} | {o['n']} | {f(o['bid_skip']['f1'])} | {f(o['bid_skip']['precision'])} | {f(o['bid_skip']['recall'])} | "
                   f"{f(o['scam']['precision'])} | {f(o['scam']['recall'])} | {f(o['price_in_fair_band'])} | "
                   f"{f(o['injection_detected_rate'])} | {f(o['latency_p95_s'], 1)} | {f(o['usd_per_job'], 5)} |")
    return "\n".join(out)


def multi_table() -> str:
    d = load("multiagent_compare.json")
    if not d or "by_arch" not in d:
        return "*pending*"
    out = ["| Architecture | Jobs | Bid/skip accuracy | Scam recall | Proposals | Unsupported / proposal | Compliance violations / proposal | Mean p(reply) | Tokens / job | p95 s |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for a, s in d["by_arch"].items():
        out.append(f"| {a} | {s['n']} | {f(s['bid_skip_accuracy'])} | {f(s['scam_recall'])} | {s['proposals']} | {f(s['unsupported_per_proposal'], 2)} | "
                   f"{f(s['compliance_violations_per_proposal'], 2)} | {f(s['mean_p_reply'], 2)} | {f(s['tokens_per_job'], 0)} | {f(s['latency_p95_s'], 0)} |")
    return "\n".join(out)


def tools_table() -> str:
    d = load("tool_granularity.json")
    out = ["| Tool set | Tools | Tool-selection accuracy | Argument accuracy | Tokens / task |", "|---|---|---|---|---|"]
    for r in d["results"]:
        out.append(f"| {r['set']} | {r['n_tools']} | {f(r['tool_selection_accuracy'])} | {f(r['argument_accuracy'])} | {f(r['tokens_per_task'], 0)} |")
    return "\n".join(out) + f"\n\n*{d['meta']['n_tasks']} tasks, model {d['results'][0]['model']}.*"


BLOCKS = {"evals/results/rag_retrieval.json": rag_table, "evals/results/gigsim_outcomes.json": b5_table,
          "evals/results/decision.json": decision_table, "evals/results/multiagent_compare.json": multi_table,
          "evals/results/tool_granularity.json": tools_table}


def main() -> None:
    p = ROOT / "README.md"
    s = p.read_text(encoding="utf-8")
    for key, fn in BLOCKS.items():
        # a block's body may never contain another block's start marker (prevents spanning into the next block)
        pat = re.compile(rf"(<!-- results:{re.escape(key)} -->\n)((?:(?!<!-- results:).)*?)(<!-- /results -->)", re.S)
        if pat.search(s):
            s = pat.sub(lambda m, fn=fn: m.group(1) + fn() + "\n" + m.group(3), s)
    p.write_text(s, encoding="utf-8")
    print("README tables rendered")


if __name__ == "__main__":
    main()
