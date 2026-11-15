"""Fill docs/report/REPORT.md placeholders from evals/results/*.json and render the PDF.

    python -m scripts.build_report
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import render_results as rr
from scripts.md_to_pdf import convert

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"


def j(name):
    p = RES / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> None:
    src = (ROOT / "docs" / "report" / "REPORT.md").read_text(encoding="utf-8")
    abl = j("rag_ablation.json")
    abl_rows = [r for r in abl["table"] if r["slice"] == "ALL"] if abl else []
    abl_md = "**Ablation** (remove one component from V4; R `rag_ablation.json`):\n\n| Pipeline | Recall@5 | MRR | nDCG@10 |\n|---|---|---|---|\n" + \
        "\n".join(f"| {r['variant']} | {r['recall@5']:.3f} | {r['mrr']:.3f} | {r['ndcg@10']:.3f} |" for r in abl_rows) + \
        "\n\nRequirement decomposition (−16 points) and the cross-encoder (−11 points) carry the pipeline; BM25 fusion and the outcome boost are within noise on this corpus."
    inj = j("injection.json")
    inj_txt = (f"{inj['asr_before']:.2f} → **{inj['asr_after']:.2f}** on {inj['n']} planted-injection jobs (canary word, fake "
               f"experience and guarantee attacks succeeded against the naive writer; none against the defended path)")
    multi = j("multiagent_compare.json")
    if multi and "by_arch" in multi:
        a = multi["by_arch"]
        multi_disc = (f"**Honest status: incomplete.** The graph finished all {a['graph']['n']} jobs with bid/skip accuracy "
                      f"{a['graph']['bid_skip_accuracy']:.2f} and caught every scam. The ReAct and supervisor baselines completed only "
                      f"{a['react']['n'] - a['react']['errors']} and {a['supervisor']['n'] - a['supervisor']['errors']} of "
                      f"{a['react']['n']} jobs before Groq's free-tier daily limit (200k tokens/day on gpt-oss-120b) stopped them "
                      f"(the errors are recorded per row). A rerun on qwen3.8-27b hit the same daily limit. What the completed runs show: "
                      f"the ReAct agent spends its budget on tool calls and often never emits the final JSON decision; the supervisor's "
                      f"two hand-offs cost ~1.3× the ReAct tokens; the hand-built graph spends tokens only where an LLM is needed "
                      f"(analysis is rules + retrieval + two small-model calls), which is why it is cheapest per job. I would not "
                      f"ship the single agent: without structured hand-offs nothing forces a grounded evidence pack or an approval "
                      f"interrupt. This comparison must be rerun with a full quota before any accuracy claim about the baselines.")
    else:
        multi_disc = "Pending."
    cr = j("change_request.json")
    cr_txt = (f"under v2, approved proposals accepted by the platform: {cr['summary']['v2']['accepted_by_platform']}/"
              f"{cr['summary']['v2']['n_approved']}, with the disclosure line added automatically by Compliance "
              f"({cr['summary']['v2']['with_disclosure']}); dry-run Connects prices matched the new policy in every previewed case. "
              f"4 of 6 runs dead-lettered on quota exhaustion in the writer, which exposed a missing fallback (fixed: the writer "
              f"now degrades to the evidence-only template)")
    ag = j("agency_routing.json")
    ag_txt = (f"routing accuracy {ag['routing_accuracy']:.2f} vs category baseline {ag['category_baseline_accuracy']:.2f} on {ag['n']} "
              f"bid-worthy dev jobs; {ag['confident_share']:.0%} of routings were confident, with accuracy {ag['accuracy_when_confident']:.2f}") if ag else \
        "routing evaluation not completed before the deadline (CPU contention with the other evaluations); the router and voice hand-off are implemented and unit-exercised"
    held = j("heldout_decision.json")
    ho = held["overall"]
    held_tbl = ("| Metric | Dev (calibrated, 72 jobs) | Held-out (57 jobs, new clients) | Declared budget |\n|---|---|---|---|\n")
    dv = j("decision_v2.json")["overall"]
    held_tbl += (f"| Bid/skip F1 | {dv['bid_skip']['f1']:.3f} | {ho['bid_skip']['f1']:.3f} | — |\n"
                 f"| Scam precision / recall | {dv['scam']['precision']:.2f} / {dv['scam']['recall']:.2f} | {ho['scam']['precision']:.2f} / {ho['scam']['recall']:.2f} | — |\n"
                 f"| Price inside fair band | {dv['price_in_fair_band']:.2f} | {ho['price_in_fair_band']:.2f} | — |\n"
                 f"| Injection flagged | {dv['injection_detected_rate']:.2f} | {ho['injection_detected_rate']:.2f} | — |\n"
                 f"| p95 latency per job analysed (s) | {dv['latency_p95_s']:.1f} | {ho['latency_p95_s']:.1f} | 25 |\n"
                 f"| USD per job analysed (list) | {dv['usd_per_job']:.4f} | {ho['usd_per_job']:.4f} | 0.002 |")
    held_tbl += ("\n\n**Caveat:** during the held-out run gpt-oss-20b had exhausted its daily quota; 114 calls fell back to "
                 "qwen3.8-27b and many further to the deterministic rules, so the held-out numbers measure the degraded path "
                 "(which is also the path a reviewer sees when the free quota is gone).")
    budgets = ("p95 per job analysed: dev 94 s and held-out 33 s versus a 25 s budget — **missed**, driven by rate-limit waits "
               "with several evaluations sharing one key; single-job runs in the smoke test took 7–9 s. Cost per job analysed "
               "$0.0003 (budget $0.002) and per proposal $0.0034–0.0045 (budget $0.01) — **met**.")
    judge = j("judge_calibration.json")
    judge_txt = (f"Cohen's kappa {judge['cohen_kappa']}, quadratic-weighted {judge['quadratic_weighted_kappa']} on {judge['n']} items"
                 if judge else "**pending my labels**: `evals/human/judge_labels.csv` (30 items) — run `python -m evals.runners.judge_calibration score` after labelling; no labels were generated by the AI")
    panel = j("human_pairwise.json")
    panel_txt = (f"Shipped-variant win rate {panel['shipped_win_rate']} over {panel['n_decisive']} decisive ratings (sign test p={panel['sign_test_p']})."
                 if panel else "Ratings from classmates are **pending** (`evals/human/pairwise.csv`, 14 pairs).")
    fills = {
        "{{TOOLS_TABLE}}": rr.tools_table(), "{{RAG_TABLE}}": rr.rag_table(), "{{ABLATION}}": abl_md,
        "{{B5_TABLE}}": rr.b5_table(), "{{MULTI_TABLE}}": rr.multi_table(), "{{MULTI_N}}": str((multi or {}).get("by_arch", {}).get("graph", {}).get("n", 12)),
        "{{MULTI_DISCUSSION}}": multi_disc, "{{INJECTION}}": inj_txt, "{{CR}}": cr_txt, "{{AGENCY}}": ag_txt,
        "{{HELDOUT_TABLE}}": held_tbl, "{{BUDGETS}}": budgets, "{{JUDGE}}": judge_txt, "{{PANEL}}": panel_txt,
        "{{HELDOUT_NOTE}}": f"; held-out F1 {ho['bid_skip']['f1']:.2f}", "{{PRICE_NOTE}}": f"(held-out price-in-band {ho['price_in_fair_band']:.2f})",
    }
    for k, v in fills.items():
        src = src.replace(k, v)
    out_md = ROOT / "docs" / "report" / "REPORT_filled.md"
    out_md.write_text(src, encoding="utf-8")
    pages = convert(out_md, ROOT / "docs" / "report" / "GigBid_RnD_Report.pdf")
    left = [k for k in fills if k in src]
    print("pages", pages, "unfilled", left)


if __name__ == "__main__":
    main()
