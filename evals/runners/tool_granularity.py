"""R&D question A — does tool granularity change agent behaviour?

40 tasks with a known correct first tool call. Three tool sets are offered to the same model:
  fine     every GigBid MCP tool exactly as published (16 tools, terse SDK descriptions)
  coarse   3 umbrella tools (marketplace_read / marketplace_write / portfolio) taking an `action` + `params`
  best     a curated 8-tool set with rewritten descriptions (when to use, argument examples)
Metrics: tool-selection accuracy, argument accuracy (key args correct), tokens per task.

    python -m evals.runners.tool_granularity
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx

from common.config import model_for, profile
from common.llm import _provider
from evals.harness import write

TASKS: list[tuple[str, str, dict]] = []
_jobs = ["job-dev-ai-003", "job-dev-fu-010", "job-dev-da-021", "job-dev-ai-044", "job-dev-fu-077"]
for j in _jobs:
    TASKS.append((f"Open job {j} and show me the full post.", "get_job", {"job_id": j}))
for c in ["cl-0012", "cl-0145", "cl-0301"]:
    TASKS.append((f"Is client {c} trustworthy? Check their marketplace history.", "get_client_history", {"client_id": c}))
for q in ["background workers that retry failed jobs", "Celery", "dbt models with tests", "Pinecone vector search",
          "a churn model for a telecom", "Stripe subscriptions", "Power BI dashboards for executives"]:
    TASKS.append((f"Do I have portfolio proof of {q}?", "search_evidence", {"requirement": q}))
for cat in ["ai_ml", "web", "data"]:
    TASKS.append((f"What do {cat} jobs usually pay per hour on the marketplace?", "get_market_stats", {"category": cat}))
TASKS += [("How many Connects do I have left this week?", "get_connects_balance", {}),
          ("What are the current platform rules for proposals?", "get_policy", {}),
          ("Show my client conversations.", "list_threads", {}),
          ("Read the messages in thread th-1a2b3c4d5e.", "list_messages", {"thread_id": "th-1a2b3c4d5e"}),
          ("Any new pipeline events since event 12?", "list_events", {"since": 12}),
          ("Which skills does my portfolio prove?", "list_skills", {}),
          ("Show me the full case study ai-07.", "get_case_study", {"case_id": "ai-07"}),
          ("Find new AI/ML jobs about RAG chatbots.", "search_jobs", {"category": "ai_ml"}),
          ("Search jobs mentioning Shopify.", "search_jobs", {"query": "Shopify"}),
          ("List my proposals and their status.", "list_proposals", {}),
          ("For job job-dev-ai-003, map each requirement to my evidence: Python, RAG, FastAPI.", "requirement_matrix",
           {"requirements": None}),
          ("Preview (do not send) a proposal draft for job job-dev-ai-003 at $900 fixed.", "create_proposal_draft",
           {"job_id": "job-dev-ai-003", "dry_run": True}),
          ("Which free slots do I have for a 30-minute interview this week?", "free_slots", {}),
          ("What's the status of everything I've submitted?", "list_proposals", {}),
          ("Check whether I have evidence for 'OCR of scanned invoices'.", "search_evidence", {"requirement": "OCR"}),
          ("Does client cl-0099 have verified payment?", "get_client_history", {"client_id": "cl-0099"}),
          ("How much is a medium data project worth?", "get_market_stats", {"category": "data"}),
          ("Get job job-dev-da-005.", "get_job", {"job_id": "job-dev-da-005"}),
          ("Have I ever built anything with LangGraph?", "search_evidence", {"requirement": "LangGraph"}),
          ("Look up the hiring history of client cl-0222 before I bid.", "get_client_history", {"client_id": "cl-0222"}),
          ("Find data analytics jobs.", "search_jobs", {"category": "data"}),
          ("Am I allowed to put a link to my website in proposals now?", "get_policy", {})]
TASKS = TASKS[:40]


def _fine_tools() -> list[dict]:
    import json as _j
    from pathlib import Path

    out = []
    for f in ["portfolio", "marketplace", "workspace"]:
        for t in _j.loads((Path(__file__).resolve().parents[2] / "tests" / "contract" / "snapshots" / f"{f}.json").read_text()):
            if t["name"] in ("send_message", "submit_proposal", "create_interview_hold", "create_email_draft", "list_holds"):
                continue
            schema = {k: v for k, v in t["inputSchema"].items() if k in ("type", "properties", "required", "$defs")}
            out.append({"type": "function", "function": {"name": t["name"], "description": t["description"][:300], "parameters": schema}})
    return out


COARSE = [
    {"type": "function", "function": {"name": "marketplace_read", "description": "Read anything from the marketplace.",
     "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "one of: search_jobs, get_job, get_client_history, get_connects_balance, get_market_stats, get_policy, list_threads, list_messages, list_events, list_proposals"},
                                                       "params": {"type": "object"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "marketplace_write", "description": "Write to the marketplace.",
     "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "create_proposal_draft"}, "params": {"type": "object"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "portfolio", "description": "Query the freelancer's portfolio and calendar.",
     "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "one of: search_evidence, requirement_matrix, get_case_study, list_skills, free_slots"}, "params": {"type": "object"}}, "required": ["action"]}}},
]

BEST_DESC = {
    "search_jobs": "Find open jobs. Use for 'find/search jobs'. Args: query (keywords, e.g. 'Shopify'), category (ai_ml|web|data).",
    "get_job": "Get ONE job's full post by id, e.g. job_id='job-dev-ai-003'. Use when the user names a job id.",
    "get_client_history": "Client trust check: spend, hires, rating, payment verification. Arg client_id like 'cl-0012'.",
    "get_connects_balance": "How many Connects are left this week. No args.",
    "get_market_stats": "Typical prices for a category (ai_ml|web|data): hourly percentiles and fixed price by size.",
    "search_evidence": "Search the portfolio for proof of ONE skill/requirement, e.g. requirement='Celery'.",
    "requirement_matrix": "Map SEVERAL requirements at once to evidence. Arg requirements=['Python','RAG',...].",
    "list_proposals": "List the user's proposals and statuses. No args.",
}


def _best_tools() -> list[dict]:
    fine = {t["function"]["name"]: t for t in _fine_tools()}
    out = []
    for n, d in BEST_DESC.items():
        t = json.loads(json.dumps(fine[n]))
        t["function"]["description"] = d
        out.append(t)
    for n in ("get_policy", "list_threads", "list_messages", "list_events", "list_skills", "get_case_study",
              "create_proposal_draft", "free_slots"):
        if n in fine:
            out.append(fine[n])
    return out


def score(expected_tool: str, expected_args: dict, call: dict | None, coarse: bool) -> tuple[bool, bool]:
    if not call:
        return False, False
    name, args = call["name"], call["args"]
    if coarse:
        name, args = args.get("action", ""), args.get("params") or {}
    ok_tool = name == expected_tool
    ok_args = ok_tool
    if ok_tool:
        for k, v in expected_args.items():
            got = args.get(k)
            if v is None:
                ok_args = ok_args and bool(got)
            elif isinstance(v, str) and k in ("requirement", "query"):
                ok_args = ok_args and isinstance(got, str) and v.lower().split()[0] in got.lower()
            else:
                ok_args = ok_args and got == v
    return ok_tool, ok_args


async def run_set(name: str, tools: list[dict], coarse: bool) -> dict:
    base, key = _provider()
    model = model_for("analyst")
    rows = []
    async with httpx.AsyncClient(timeout=60) as c:
        for prompt_, tool, args in TASKS:
            payload = {"model": model, "messages": [
                {"role": "system", "content": "You are GigBid's assistant. Call exactly one tool to start the user's task."},
                {"role": "user", "content": prompt_}], "tools": tools, "tool_choice": "required", "max_tokens": 300}
            if model.startswith("openai/gpt-oss"):
                payload["reasoning_effort"] = "low"
            for _attempt in range(6):
                r = await c.post(f"{base}/chat/completions", json=payload, headers={"Authorization": f"Bearer {key}"})
                if r.status_code == 429:
                    await asyncio.sleep(float(r.headers.get("retry-after", 5)) + 1)
                    continue
                break
            call = None
            usage = {}
            if r.status_code == 200:
                d = r.json()
                usage = d.get("usage", {})
                tc = (d["choices"][0]["message"].get("tool_calls") or [None])[0]
                if tc:
                    try:
                        call = {"name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"] or "{}")}
                    except json.JSONDecodeError:
                        call = {"name": tc["function"]["name"], "args": {}}
            ok_t, ok_a = score(tool, args, call, coarse)
            rows.append({"task": prompt_, "expected": tool, "call": call, "tool_ok": ok_t, "args_ok": ok_a,
                         "tokens": usage.get("total_tokens", 0), "http": r.status_code})
    n = len(rows)
    return {"set": name, "n_tools": len(tools), "n": n, "tool_selection_accuracy": round(sum(r["tool_ok"] for r in rows) / n, 3),
            "argument_accuracy": round(sum(r["args_ok"] for r in rows) / n, 3),
            "tokens_per_task": round(sum(r["tokens"] for r in rows) / n, 1), "model": model, "rows": rows}


async def main_async() -> None:
    res = [await run_set("fine", _fine_tools(), False), await run_set("coarse", COARSE, True),
           await run_set("best", _best_tools(), False)]
    write("tool_granularity", {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "n_tasks": len(TASKS),
                                        "provider": profile().get("provider")}, "results": res})
    for r in res:
        print(r["set"], r["n_tools"], r["tool_selection_accuracy"], r["argument_accuracy"], r["tokens_per_task"])


if __name__ == "__main__":
    asyncio.run(main_async())
