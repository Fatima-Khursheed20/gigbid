"""Run the four required scenarios with LangSmith tracing on and create PUBLIC share links.

    python -m scripts.langsmith_traces      # needs LANGSMITH_API_KEY in .env
Writes evals/results/langsmith_traces.json and docs/TRACES.md section.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

from dotenv import dotenv_values

from common.settings import ROOT

env = dotenv_values(ROOT / ".env")
os.environ.update({"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": env["LANGSMITH_API_KEY"],
                   "LANGSMITH_PROJECT": env.get("LANGSMITH_PROJECT") or "gigbid", "LLM_OFFLINE": "0"})


async def main() -> None:
    from langsmith import Client

    from agent import runtime
    from agent.nodes._base import UserProfile
    from evals.harness import load_dev, setup_inprocess

    setup_inprocess()
    rows = {r["job_id"]: r for r in load_dev("ai_ml")}
    prof = UserProfile(user_id="trace-demo", tenant="ai_ml", hourly_rate=45, floor_rate=30, min_project=300,
                       voice="direct, technical, numbers-first")

    async def run(job_id, tag, **kw):
        tid = f"bid:trace-demo:{job_id}"
        res = await runtime.run_graph("bid", profile=prof, thread_id=tid, mode="inprocess", marketplace_token="gs-trace-demo",
                                      dsn="", **kw)
        return {"scenario": tag, "job_id": job_id, "trace_id": res["trace_id"], "status": res["state"].get("status"),
                "critic_rounds": len(res["state"].get("critiques", []))}

    out = [await run("job-dev-ai-000", "skipped scam", inp={"job_id": "job-dev-ai-000"})]
    first = await run("job-dev-ai-105", "proposal drafted (waits for approval)", inp={"job_id": "job-dev-ai-105"})
    out.append(first)
    # crash-and-resume: the process that drafted is gone; a fresh graph object resumes from the checkpoint
    runtime_saver = runtime._MEM["saver"]
    runtime.reset_memory()
    runtime._MEM["saver"] = runtime_saver  # same durable checkpoint store, brand-new graph and deps
    out.append(await run("job-dev-ai-105", "approved after resume (crash-and-resume)", resume={"action": "approve"}))
    out.append(await run("job-dev-ai-186", "critic loop", inp={"job_id": "job-dev-ai-186"}))
    time.sleep(8)  # let the tracer flush
    c = Client()
    proj = os.environ["LANGSMITH_PROJECT"]
    for o in out:
        runs = list(c.list_runs(project_name=proj, is_root=True, filter=f'has(metadata, \'{{"trace_id": "{o["trace_id"]}"}}\')',
                                limit=5))
        if runs:
            o["run_id"] = str(runs[0].id)
            o["public_url"] = c.share_run(runs[0].id)
        print(o)
    (ROOT / "evals" / "results" / "langsmith_traces.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
