"""Fit Matcher: map every requirement to portfolio evidence through the Portfolio MCP server's corrective
retrieval (requirement_matrix) and score fit with reasons. Runs in parallel with the Analyst, so it extracts
requirements itself (the same offline decomposition the retriever was evaluated with)."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from rag.pipeline import heuristic_requirements
from rag.skills import extract_skills

from ..handoffs import EvidenceRef, FitReport, RequirementEvidence
from ._base import deps, node

WEIGHT = {"supported": 1.0, "weak": 0.35, "none": 0.0}


def fit_from_matrix(rows: list[dict], job_text: str) -> FitReport:
    matrix = []
    for r in rows:
        ev = [EvidenceRef(evidence_id=e["evidence_id"], project_id=e.get("project_id"), project=e.get("project"),
                          type=e.get("type"), snippet=(e.get("text") or "")[:400], score=e.get("score", 0.0))
              for e in r.get("evidence", [])]
        matrix.append(RequirementEvidence(requirement=r["requirement"], status=r["status"], evidence=ev))
    from common.config import cfg

    weights = {**WEIGHT, "weak": float(cfg("rag", "weak_weight", default=WEIGHT["weak"]))}
    score = sum(weights[m.status] for m in matrix) / max(1, len(matrix))
    job_sk = set(extract_skills(job_text))
    have = {s for m in matrix if m.status == "supported" for e in m.evidence for s in extract_skills(e.snippet)}
    reasons = [f"{sum(m.status == 'supported' for m in matrix)}/{len(matrix)} requirements have direct portfolio evidence"]
    missing = [m.requirement for m in matrix if m.status == "none"]
    if missing:
        reasons.append("No evidence for: " + "; ".join(x[:60] for x in missing[:3]))
    return FitReport(score=round(score, 3), matrix=matrix, matched_skills=sorted(job_sk & have),
                     missing_skills=sorted(job_sk - have), reasons=reasons)


@node("fit_matcher", timeout_s=120)
async def fit_matcher(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    job = state["job"]
    text = f"{job['title']}\n\n{job['description']}"
    reqs = heuristic_requirements(text)[:8]
    res = await d.bus.call("fit_matcher", "requirement_matrix", {"requirements": reqs})
    fit = fit_from_matrix(res["rows"], text)
    return {"fit": fit.model_dump(), "analyses_done": ["fit"]}
