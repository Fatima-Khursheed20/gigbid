"""Claim verification node (B3): runs between the Writer and the Critic."""

from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig

from rag.verify import verify_claims

from ._base import node


@node("verifier", timeout_s=120)
async def verifier(state: dict, config: RunnableConfig) -> dict:
    draft = dict(state["draft"])
    ev = state.get("evidence", [])
    res = await verify_claims(draft["cover_letter"], ev)
    answers = []
    ans_before = ans_after = {"claims": 0, "unsupported": 0}
    for a in draft.get("screening_answers", []):
        r = await verify_claims(a["answer"], ev) if a.get("answer") else {"text": "", "before": ans_before, "after": ans_after}
        answers.append({"question": a["question"], "answer": r["text"] or "I'd rather discuss this on a short call."})
        ans_before = {k: ans_before[k] + r["before"][k] for k in ("claims", "unsupported")}
        ans_after = {k: ans_after[k] + r["after"][k] for k in ("claims", "unsupported")}
    draft.update(cover_letter=res["text"], screening_answers=answers, claims=res["claims"],
                 word_count=len(re.sub(r"\[E\d+\]", "", res["text"]).split()))
    before = {k: res["before"][k] + ans_before.get(k, 0) for k in ("claims", "unsupported")}
    after = {k: res["after"][k] + ans_after.get(k, 0) for k in ("claims", "unsupported")}
    ver = {"before": before, "after": after, "partly_before": res["before"]["partly_supported"], "changed": res["changed"]}
    return {"draft": draft, "verification": ver, "status": "critiquing"}
