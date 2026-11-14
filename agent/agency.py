"""Signature extension X1 — Agency mode: a team of freelancers; route each job to the best-fit member.

Routing uses each member's Portfolio MCP corrective retrieval (requirement_matrix) to score fit, then picks the
member with the highest fit (ties broken by hourly-rate fit to the client's budget). The bid graph then runs
for that member's tenant, and the Writer drafts in that member's voice (profile.voice).
"""

from __future__ import annotations

from rag.pipeline import heuristic_requirements

from .mcp_client import ToolBus
from .nodes.fit_matcher import fit_from_matrix


async def route(job: dict, members: list[str], *, user_id: str = "agency", mode: str = "http") -> dict:
    text = f"{job['title']}\n\n{job['description']}"
    reqs = heuristic_requirements(text)[:8]
    scores = {}
    for m in members:
        async with ToolBus(user_id=user_id, tenant=m, mode=mode) as bus:
            res = await bus.call("fit_matcher", "requirement_matrix", {"requirements": reqs})
        scores[m] = fit_from_matrix(res["rows"], text).score
    best = max(scores, key=scores.get)
    return {"member": best, "scores": scores, "confident": scores[best] - sorted(scores.values())[-2] >= 0.1}
