"""30-job smoke eval with failure thresholds (E2). Runs in CI on every pull request.

    python -m evals.runners.smoke_eval            # uses the LLM if GROQ_API_KEY is set, else offline gates
"""

from __future__ import annotations

import asyncio
import json
import sys

import yaml

from common import llm
from common.settings import ROOT
from evals.harness import write
from evals.runners import decision_eval, gigsim_outcomes


def main() -> int:
    online = llm.available()
    th = yaml.safe_load((ROOT / "evals" / "thresholds.yaml").read_text())["online" if online else "offline"]
    asyncio.run(decision_eval.main_async(10, offline=not online, out="smoke_decision"))
    dec = json.loads((ROOT / "evals" / "results" / "smoke_decision.json").read_text())["overall"]
    asyncio.run(gigsim_outcomes.main_async(["v4_outcome"], 1, "smoke_outcomes"))
    out = json.loads((ROOT / "evals" / "results" / "smoke_outcomes.json").read_text())["by_variant"]["v4_outcome"]
    checks = {
        "bid_skip_f1": (dec["bid_skip"]["f1"], dec["bid_skip"]["f1"] >= th["bid_skip_f1_min"]),
        "scam_recall": (dec["scam"]["recall"], dec["scam"]["recall"] >= th["scam_recall_min"]),
        "unsupported_claims_after": (out["unsupported_per_proposal_after"],
                                     (out["unsupported_per_proposal_after"] or 0) <= th["unsupported_claims_per_proposal_max"]),
    }
    write("smoke_gate", {"online": online, "thresholds": th, "checks": {k: {"value": v, "pass": ok} for k, (v, ok) in checks.items()}})
    for k, (v, ok) in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {k} = {v}")
    return 0 if all(ok for _, ok in checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
