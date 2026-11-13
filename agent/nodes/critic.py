"""Critic: grounding, personalisation, length; sends the draft back with reasons at most twice (C4)."""

from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig

from common import llm
from common.config import cfg, prompt

from ..handoffs import Critique, CritiqueIssue
from ._base import node

GENERIC = re.compile(r"(?i)^(dear|hello|hi|greetings|to whom|i am writing|i have read|i am a passionate|i am very interested|"
                     r"i can do this)")


def rule_issues(draft: dict, job: dict) -> list[CritiqueIssue]:
    text = draft["cover_letter"]
    issues = []
    words = len(re.sub(r"\[E\d+\]", "", text).split())
    lo, hi = cfg("thresholds", "proposal_min_words", default=80), cfg("thresholds", "proposal_max_words", default=220)
    if words > hi:
        issues.append(CritiqueIssue(kind="length", detail=f"{words} words; cut to under {hi}."))
    if words < lo:
        issues.append(CritiqueIssue(kind="length", detail=f"{words} words; too thin, add one concrete proof point."))
    if GENERIC.search(text.strip()):
        issues.append(CritiqueIssue(kind="generic_opening", detail="Opens with a generic greeting; start with the client's problem."))
    if not re.search(r"\[E\d+\]", text):
        issues.append(CritiqueIssue(kind="grounding", detail="No evidence citations; cite at least one project."))
    unanswered = [q for q in job.get("screening_questions") or []
                  if not any(a["question"] == q and a["answer"].strip() for a in draft.get("screening_answers", []))]
    if unanswered:
        issues.append(CritiqueIssue(kind="screening", detail=f"Unanswered screening question(s): {unanswered}"))
    return issues


@node("critic", timeout_s=90)
async def critic(state: dict, config: RunnableConfig) -> dict:
    draft, job = state["draft"], state["job"]
    rnd = state.get("revisions", 0)
    issues = rule_issues(draft, job)
    score = 0.7
    instructions = ""
    if llm.available():
        try:
            c = await llm.structured("critic", prompt("critic"),
                                     f"Job title: {job['title']}\nScreening questions: {job.get('screening_questions')}\n\n"
                                     f"DRAFT:\n{draft['cover_letter']}\n\nANSWERS: {draft.get('screening_answers')}", Critique,
                                     max_tokens=600)
            issues += [i for i in c.issues if i.kind in ("personalisation", "tone", "grounding", "other")]
            score, instructions = c.score, c.revision_instructions
        except Exception:  # noqa: BLE001 - fall back to rule critique
            pass
    approve = not issues
    if not instructions and issues:
        instructions = " ".join(i.detail for i in issues)
    crit = Critique(approve=approve, issues=issues, revision_instructions=instructions, round=rnd, score=score)
    return {"critiques": [crit.model_dump()], "status": "compliance" if approve else "revising"}
