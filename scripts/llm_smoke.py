"""LLM smoke run of the real bid graph on a few dev jobs (prints node events as they happen)."""

from __future__ import annotations

import asyncio
import faulthandler
import json
import os
import sys
import time

os.environ["LLM_OFFLINE"] = "0"
faulthandler.dump_traceback_later(240, repeat=False, file=sys.stderr)


async def main(kinds: list[str], persona: str) -> None:
    from agent import tracebus
    from evals.harness import load_dev, run_job, setup_inprocess

    setup_inprocess()
    rows = load_dev(persona)
    orig = tracebus.record

    async def loud(kind, node, **data):
        if kind in ("node_start", "node_end", "tool_error", "tool_unreachable"):
            print(f"  {time.strftime('%H:%M:%S')} {kind} {node} {data.get('latency_s', '')} {data.get('status', '') or ''}"
                  f" {data.get('error', '')}", flush=True)
        await orig(kind, node, **data)

    tracebus.record = loud
    for k in kinds:
        j = next(r for r in rows if r["gold"]["kind"] == k and (k != "fit" or r["gold"]["bid"]))
        print("==", j["job_id"], k, j["gold"].get("injection_type"), flush=True)
        r = await run_job(persona, j)
        st = r["state"]
        print("status", st.get("status"), "lat", r["latency_s"], "tok", r["tokens"], "usd", r["usd"])
        print("decision", st.get("decision", {}).get("action"), "fit", st.get("fit", {}).get("score"),
              "risk", st.get("risk", {}).get("score"), st.get("risk", {}).get("flags"))
        print("by_node", json.dumps(r["by_node"]))
        if st.get("draft"):
            print("verification", st.get("verification"), "critic", [c["approve"] for c in st.get("critiques", [])])
            print(st["draft"]["cover_letter"])
        print("errors", st.get("errors"), flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].split(","), sys.argv[2] if len(sys.argv) > 2 else "ai_ml"))
