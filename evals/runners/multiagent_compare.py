"""R&D question C — is the multi-agent design worth it?

(a) one ReAct agent holding all (read) tools, (b) prebuilt langgraph-supervisor with researcher + writer workers,
(c) GigBid's hand-built graph. Same MCP tools, same strong model for drafting, same jobs.
Metrics: bid/skip accuracy, scam caught, unsupported claims per proposal (same verifier + same evidence pack for
all three), compliance violations in what each would send, GigSim simulated reply, tokens, latency.

    python -m evals.runners.multiagent_compare --per-persona 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

from agent.nodes.compliance import check_text
from agent.nodes.fit_matcher import fit_from_matrix
from agent.nodes.writer import evidence_pack
from common import llm
from common.config import prompt
from evals.harness import (
    PERSONAS,
    PROFILE_ARGS,
    load_dev,
    mean,
    pct,
    run_job,
    setup_inprocess,
    stratified,
    write,
)
from mcp_servers.portfolio import tools as PT
from rag.pipeline import heuristic_requirements
from rag.verify import label_claims, rate


def _final_json(text: str) -> dict:
    m = re.findall(r"\{.*\}", text or "", flags=re.S)
    for cand in reversed(m):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return {}


def _tokens(messages) -> int:
    return sum((getattr(m, "usage_metadata", None) or {}).get("total_tokens", 0) for m in messages)


async def run_baseline(kind: str, persona: str, job: dict) -> dict:
    from langgraph.prebuilt import create_react_agent

    from agent.mcp_client import ToolBus

    model = llm.chat_model("baseline_agent")
    ask = (f"Job id: {job['job_id']}. Freelancer: hourly rate ${PROFILE_ARGS[persona]['hourly_rate']}, floor "
           f"${PROFILE_ARGS[persona]['floor_rate']}/h, minimum project ${PROFILE_ARGS[persona]['min_project']}.")
    t0 = time.perf_counter()
    async with ToolBus(user_id=f"cmp-{kind}-{persona}", tenant=persona, mode="inprocess") as bus:
        tools = [t for t in await bus.langchain_tools("baseline") if t.name != "create_proposal_draft"]
        if kind == "react":
            agent = create_react_agent(model, tools, prompt=prompt("baseline_agent"))
        else:
            from langgraph_supervisor import create_supervisor

            researcher = create_react_agent(model, tools, prompt=prompt("researcher"), name="researcher")
            writer = create_react_agent(model, [], prompt=prompt("baseline_agent"), name="writer")
            agent = create_supervisor([researcher, writer], model=model, prompt=prompt("supervisor")).compile()
        out = await agent.ainvoke({"messages": [{"role": "user", "content": ask}]}, {"recursion_limit": 30})
    msgs = out["messages"]
    final = _final_json(msgs[-1].content if msgs else "")
    return {"decision": final.get("decision"), "scam": bool(final.get("scam")), "proposal": final.get("proposal") or "",
            "price": final.get("price"), "tokens": _tokens(msgs), "latency_s": round(time.perf_counter() - t0, 2),
            "tool_calls": sum(len(getattr(m, "tool_calls", []) or []) for m in msgs)}


async def run_graph(persona: str, job: dict) -> dict:
    r = await run_job(persona, job, user="cmp-graph")
    st = r["state"]
    return {"decision": (st.get("decision") or {}).get("action"), "scam": bool((st.get("risk") or {}).get("scam")),
            "proposal": re.sub(r"\s?\[E\d+\]", "", (st.get("draft") or {}).get("cover_letter", "")),
            "price": (st.get("price") or {}).get("amount"), "tokens": r["tokens"], "latency_s": r["latency_s"],
            "tool_calls": sum(1 for e in r["events"] if e["kind"] == "tool_call")}


async def main_async(per: int, model: str | None = None) -> None:
    import gigsim.app as gs
    from gigsim import client_model

    setup_inprocess()
    if model:  # same drafting model for all three architectures (fairness / quota)
        from common.config import profile

        for node in ("writer", "critic", "liaison", "baseline_agent", "verifier"):
            profile()["nodes"][node] = model
    rows = []
    for p in PERSONAS:
        for j in stratified(load_dev(p), per, seed=31):
            text = f"{j['title']}\n\n{j['description']}"
            mat = PT.requirement_matrix(p, heuristic_requirements(text)[:8])
            ev, _ = evidence_pack(fit_from_matrix([r.model_dump() for r in mat.rows], text).model_dump())
            for kind in ("react", "supervisor", "graph"):
                try:
                    res = await (run_graph(p, j) if kind == "graph" else run_baseline(kind, p, j))
                except Exception as e:  # noqa: BLE001 - a crashed baseline is a result too
                    res = {"decision": None, "scam": False, "proposal": "", "price": None, "tokens": 0, "latency_s": None,
                           "error": f"{type(e).__name__}: {str(e)[:200]}"}
                prop = res["proposal"] if res.get("decision") == "bid" else ""
                claims = await label_claims(prop, ev) if prop else []
                comp = check_text(prop) if prop else None
                reply = None
                if prop:
                    wj = gs.WORLD.jobs[j["job_id"]]
                    reply = client_model.decide(wj, wj.get("_hidden", {}), f"cmp-{kind}", prop, float(res.get("price") or 0) or None,
                                                wj["budget_type"], bool(gs.WORLD.clients.get(wj["client_id"], {}).get("scam")))
                rows.append({"arch": kind, "persona": p, "job_id": j["job_id"], "kind": j["gold"]["kind"],
                             "gold_bid": j["gold"]["bid"], "gold_scam": j["gold"]["scam"], "pred_bid": res.get("decision") == "bid",
                             "pred_scam": res["scam"], "unsupported": rate(claims)["unsupported"] if prop else None,
                             "claims": len(claims) if prop else None,
                             "compliance_violations": len(comp.violations) if comp else 0,
                             "replied": bool(reply and reply["replied"]), "p_reply": reply["p_reply"] if reply else None,
                             "tokens": res["tokens"], "latency_s": res["latency_s"], "tool_calls": res.get("tool_calls"),
                             "error": res.get("error"), "proposal": prop})
                print(kind, j["job_id"], "gold", j["gold"]["bid"], "pred", res.get("decision"), "tok", res["tokens"],
                      res.get("error", ""), flush=True)
            write("multiagent_compare", {"rows": rows})

    def summ(rs):
        props = [r for r in rs if r["proposal"]]
        return {"n": len(rs), "bid_skip_accuracy": round(mean([float(r["pred_bid"] == r["gold_bid"]) for r in rs]) or 0, 3),
                "scam_recall": round(mean([float(r["pred_scam"]) for r in rs if r["gold_scam"]]) or 0, 3) if any(r["gold_scam"] for r in rs) else None,
                "proposals": len(props), "unsupported_per_proposal": mean([r["unsupported"] for r in props]),
                "compliance_violations_per_proposal": mean([r["compliance_violations"] for r in props]),
                "mean_p_reply": mean([r["p_reply"] for r in props]), "reply_rate": mean([float(r["replied"]) for r in props]),
                "tokens_per_job": mean([r["tokens"] for r in rs]), "latency_p50_s": pct([r["latency_s"] for r in rs], 0.5),
                "latency_p95_s": pct([r["latency_s"] for r in rs], 0.95), "errors": sum(bool(r["error"]) for r in rs)}

    res = {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "per_persona": per, "drafting_model": model},
           "by_arch": {a: summ([r for r in rows if r["arch"] == a]) for a in ("react", "supervisor", "graph")},
           "by_arch_kind": {f"{a}|{k}": summ([r for r in rows if r["arch"] == a and r["kind"] == k])
                            for a in ("react", "supervisor", "graph") for k in sorted({r["kind"] for r in rows})},
           "rows": rows}
    write("multiagent_compare", res)
    print(json.dumps(res["by_arch"], indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=4)
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    asyncio.run(main_async(a.per_persona, a.model))


if __name__ == "__main__":
    main()
