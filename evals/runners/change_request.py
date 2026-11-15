"""Change request run: GigSim "platform policy update" v2 (AI-disclosure line required, no external URLs,
featured jobs cost +2 Connects). Runs the same fixed jobs under v1 and v2 and checks that every approved
proposal is accepted by the platform and that the dry-run preview shows the new Connects price.

    python -m evals.runners.change_request --per-persona 2
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from evals.harness import write


async def run(version: str, per: int) -> list[dict]:
    os.environ["GIGSIM_POLICY_VERSION"] = version
    from evals.harness import run_job, setup_inprocess
    from evals.runners.gigsim_outcomes import fixed_jobs

    setup_inprocess()
    import gigsim.app as gs

    rows = []
    for persona, jobs in fixed_jobs(per).items():
        for j in jobs:
            r = await run_job(persona, j, approve=True, user=f"cr-{version}")
            st, after = r["state"], r.get("state_after") or {}
            text = (after.get("draft") or st.get("draft") or {}).get("cover_letter", "")
            rows.append({"policy": version, "job_id": j["job_id"], "featured": gs.WORLD.jobs[j["job_id"]]["featured"],
                         "preview_connects": (st.get("preview") or {}).get("connects_cost"),
                         "expected_connects": gs.WORLD.connects_cost(gs.WORLD.jobs[j["job_id"]]),
                         "final_status": after.get("status") or st.get("status"),
                         "has_disclosure": "drafted with ai assistance and reviewed by me." in text.lower(),
                         "has_url": "http" in text.lower(),
                         "violations_fixed": [v["rule"] for v in (st.get("compliance") or {}).get("violations", [])]})
            print(version, j["job_id"], rows[-1]["final_status"], rows[-1]["has_disclosure"], flush=True)
    return rows


async def main_async(per: int) -> None:
    rows = await run("v1", per) + await run("v2", per)
    out = {}
    for v in ("v1", "v2"):
        rs = [r for r in rows if r["policy"] == v and r["final_status"] in ("submitted", "needs_attention")]
        out[v] = {"n_approved": len(rs), "accepted_by_platform": sum(r["final_status"] == "submitted" for r in rs),
                  "preview_cost_correct": sum(r["preview_connects"] == r["expected_connects"] for r in rows if r["policy"] == v),
                  "with_disclosure": sum(r["has_disclosure"] for r in rs)}
    write("change_request", {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                      "code_lines_changed_to_absorb_v2": 0,
                                      "config_change": "GIGSIM_POLICY_VERSION=v2 on the simulator only; GigBid reads "
                                                       "submission_checks and Connects prices from get_policy/get_job",
                                      "caveat": "the change request was authored by me (instructor CR unavailable) "
                                                "before the Compliance Guard was written, so this run checks the "
                                                "config-driven design works; it is not a blind test"},
                             "summary": out, "rows": rows})
    print(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=2)
    asyncio.run(main_async(ap.parse_args().per_persona))
