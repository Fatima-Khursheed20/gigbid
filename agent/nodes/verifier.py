"""Claim verification node (B3): runs between the Writer and the Critic."""

from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig

from rag.verify import apply_labels, label_claims, rate

from ._base import node


def _combined(letter: str, answers: list[dict]) -> str:
    return letter + "".join(f"\n\nQ: {a['question']}\nA: {a['answer']}" for a in answers)


@node("verifier", timeout_s=120)
async def verifier(state: dict, config: RunnableConfig) -> dict:
    """One verification call over the cover letter AND the screening answers (token budget); each part is then
    cleaned with the same labels, and the cleaned text is re-checked only if something changed."""
    draft = dict(state["draft"])
    ev = state.get("evidence", [])
    answers = draft.get("screening_answers", [])
    combined = _combined(draft["cover_letter"], answers)
    before = await label_claims(combined, ev)
    letter, claims = apply_labels(draft["cover_letter"], [dict(c) for c in before])
    new_answers = []
    for a in answers:
        txt, _ = apply_labels(a["answer"], [dict(c) for c in before])
        new_answers.append({"question": a["question"], "answer": txt or "I'd rather discuss this on a short call."})
    combined_after = _combined(letter, new_answers)
    changed = combined_after != combined
    after = await label_claims(combined_after, ev) if changed else before
    draft.update(cover_letter=letter, screening_answers=new_answers, claims=claims,
                 word_count=len(re.sub(r"\[E\d+\]", "", letter).split()))
    rb, ra = rate(before), rate(after)
    ver = {"before": {"claims": rb["claims"], "unsupported": rb["unsupported"]},
           "after": {"claims": ra["claims"], "unsupported": ra["unsupported"]},
           "partly_before": rb["partly_supported"], "partly_after": ra["partly_supported"], "changed": changed}
    return {"draft": draft, "verification": ver, "status": "critiquing"}
