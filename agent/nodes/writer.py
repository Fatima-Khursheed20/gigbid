"""Proposal Writer: cover letter + screening answers in which every claim cites portfolio evidence [E<n>]."""

from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from common import llm
from common.config import prompt

from ..guards import delimit, neutralise
from ..handoffs import ProposalDraft, ScreeningAnswer
from ..memory.store import outcome_hints, style_rules
from ._base import deps, node


class _WriterOut(BaseModel):
    cover_letter: str
    screening_answers: list[dict] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


def evidence_pack(fit: dict, max_items: int = 8) -> tuple[list[dict], list[str]]:
    """Numbered evidence for the writer + requirements with no evidence (must not be claimed)."""
    ev, seen, none = [], set(), []
    for row in fit.get("matrix", []):
        if row["status"] == "none" or not row.get("evidence"):
            none.append(row["requirement"])
            continue
        for e in row["evidence"][:2]:
            if e["evidence_id"] not in seen and len(ev) < max_items:
                seen.add(e["evidence_id"])
                ev.append({"evidence_id": e["evidence_id"], "project_id": e.get("project_id"), "project": e.get("project"),
                           "type": e.get("type"), "text": e.get("snippet", ""), "requirement": row["requirement"]})
    return ev, none


def template_draft(job: dict, ev: list[dict], none: list[str], price: dict) -> _WriterOut:
    """Offline writer (no LLM): only restates evidence verbatim, so it cannot invent claims."""
    title = job["title"].rstrip(".")
    lines = [f"You need {title.lower()}, and I have delivered closely related work."]
    for i, e in enumerate(ev[:2]):
        res = re.search(r"(?s)## Results\s*(.+?)(\n#|$)", e["text"])
        lines = [ln.strip() for ln in (res.group(1) if res else e["text"]).splitlines()
                 if len(ln.split()) >= 6 and not ln.lstrip().startswith(("#", "*Client", "_Context", "```"))]
        detail = (lines[0] if lines else e["project"] or "related work")[:220]
        lines.append(f"On '{e['project']}' — {detail} [E{i + 1}]")
    if none:
        lines.append(f"I have not done {none[0][:60].lower()} before, so I would scope that part with you first.")
    lines.append(f"I suggest starting with a short call to confirm scope; my bid is ${price.get('amount', 0):,.0f}"
                 f"{'/h' if price.get('bid_type') == 'hourly' else ''}. What does success look like for you in month one?")
    answers = [{"question": q, "answer": f"See '{ev[0]['project']}' above [E1]." if ev else "Happy to discuss on a call."}
               for q in job.get("screening_questions") or []]
    return _WriterOut(cover_letter="\n\n".join(lines), screening_answers=answers, evidence_ids=[e["evidence_id"] for e in ev])


async def write(job: dict, spec: dict, fit: dict, price: dict, rules: list[str], hints: list[str],
                critique: dict | None, previous: str | None, voice: str = "") -> tuple[_WriterOut, list[dict]]:
    ev, none = evidence_pack(fit)
    if not llm.available():
        return template_draft(job, ev, none, price), ev
    clean, _ = neutralise(job["description"])
    ev_txt = "\n".join(f"[E{i + 1}] ({e['type']}, project: {e['project']}) {e['text'][:600]}" for i, e in enumerate(ev))
    parts = [
        "EVIDENCE (the only facts you may claim):\n" + (ev_txt or "(none)"),
        "NO EVIDENCE (do not claim): " + ("; ".join(none) or "(none)"),
        f"JobSpec: requirements={[r.get('text') for r in spec.get('requirements', [])]}; "
        f"deliverables={spec.get('deliverables')}; hidden_needs={spec.get('hidden_needs')}",
        f"Price to mention (optional): {price.get('amount')} ({price.get('bid_type')})",
        "Screening questions to answer: " + str(job.get("screening_questions") or []),
        "Learned style rules (from the user's past edits): " + ("; ".join(rules) or "(none yet)"),
        "Write in this freelancer's voice: " + (voice or "plain, specific, first person"),
        "Outcome memory: " + ("; ".join(hints) or "(none yet)"),
        delimit(f"{job['title']}\n\n{clean}"),
    ]
    if critique and previous:
        parts.append(f"PREVIOUS DRAFT:\n{previous}\n\nCRITIC FEEDBACK (fix all of it): {critique.get('revision_instructions')}")
    try:
        out = await llm.structured("writer", prompt("writer"), "\n\n".join(parts), _WriterOut, max_tokens=1400)
    except llm.LLMUnavailable:
        # provider down / daily quota exhausted (seen in the change-request run): degrade to the evidence-only
        # template instead of dead-lettering the job; the human still reviews it
        return template_draft(job, ev, none, price), ev
    return out, ev


@node("writer", timeout_s=150)
async def writer(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    job = state["job"]
    rules = await style_rules(d.store, d.profile.user_id)
    hints = await outcome_hints(d.store, d.profile.user_id, job.get("category", "other"))
    crit = state["critiques"][-1] if state.get("critiques") else None
    prev = (state.get("draft") or {}).get("cover_letter") if crit else None
    out, ev = await write(job, state.get("job_spec", {}), state.get("fit", {}), state.get("price", {}), rules, hints,
                          crit, prev, d.profile.voice)
    answers = [ScreeningAnswer(question=a.get("question", ""), answer=a.get("answer", "")) for a in out.screening_answers]
    draft = ProposalDraft(job_id=job["job_id"], cover_letter=out.cover_letter.strip(), screening_answers=answers,
                          evidence_ids=[e["evidence_id"] for e in ev], version=(state.get("draft") or {}).get("version", 0) + 1,
                          word_count=len(re.sub(r"\[E\d+\]", "", out.cover_letter).split()))
    return {"draft": draft.model_dump(), "evidence": ev, "status": "verifying"}
