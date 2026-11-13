"""Human approval gate (R4, C5) and exactly-once submission (C6).

* prepare_preview: strips citation markers and asks the marketplace for a dry_run of exactly what would be sent
  and what it costs (Connects + balance after).
* human_approval: LangGraph interrupt(). The payload carries the draft, the evidence behind every claim, the
  risk report, the price rationale and the dry_run preview. Resumes with approve / edit / reject.
* apply_edit: diff saved for style memory (through the promotion rule), then back to Compliance.
* submit: idempotency keys derived from the thread + content, so a crash/retry never submits twice.
"""

from __future__ import annotations

import hashlib
import re

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from ..handoffs import ApprovalDecision
from ..memory.promotion_rules import record_edit
from ._base import deps, node

CITE = re.compile(r"\s?\[E\d+\]")


def strip_citations(text: str) -> str:
    return CITE.sub("", text or "").strip()


def final_payload(state: dict) -> dict:
    d, p = state["draft"], state["price"]
    return {"job_id": state["job"]["job_id"], "cover_letter": strip_citations(d["cover_letter"]),
            "screening_answers": [strip_citations(a["answer"]) for a in d.get("screening_answers", [])],
            "bid_amount": float(p["amount"]), "bid_type": p["bid_type"]}


def _key(thread_id: str, kind: str, payload: dict | None = None) -> str:
    h = hashlib.sha1(repr(sorted((payload or {}).items())).encode()).hexdigest()[:10] if payload else "x"
    return f"{thread_id}:{kind}:{h}"


@node("prepare_preview", timeout_s=40)
async def prepare_preview(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    payload = final_payload(state)
    tid = config["configurable"]["thread_id"]
    dry = await d.port.create_proposal_draft("approval_gate", payload, _key(tid, "draft", payload), dry_run=True)
    bal = (await d.port.get_connects_balance("approval_gate")).get("balance")
    cost = dry.get("connects_cost") or 0
    preview = {"would_send": dry.get("would_send", payload), "connects_cost": cost, "balance_before": bal,
               "balance_after": (bal - cost) if bal is not None else None, "marketplace": d.port.mode}
    return {"preview": preview, "status": "awaiting_approval"}


@node("human_approval", timeout_s=10_000_000, retries=0)
async def human_approval(state: dict, config: RunnableConfig) -> dict:
    decision = interrupt({
        "type": "proposal_approval",
        "job": {k: state["job"].get(k) for k in ("job_id", "title", "category", "budget", "budget_type", "hourly_range")},
        "draft": state["draft"], "evidence": state.get("evidence", []), "risk": state.get("risk"),
        "fit": state.get("fit"), "price": state.get("price"), "preview": state.get("preview"),
        "critiques": state.get("critiques", []), "compliance": state.get("compliance"),
        "verification": state.get("verification"),
    })
    dec = ApprovalDecision.model_validate(decision)
    status = {"approve": "submitting", "edit": "editing", "reject": "rejected"}[dec.action]
    return {"approval": dec.model_dump(), "approvals": [dec.model_dump()], "status": status}


@node("apply_edit", timeout_s=30)
async def apply_edit(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    dec = state["approval"]
    draft = dict(state["draft"])
    before = strip_citations(draft["cover_letter"])
    after = (dec.get("edited_text") or before).strip()
    promoted = await record_edit(d.store, d.profile.user_id, state["job"]["job_id"], before, after,
                                 source=dec.get("reason") if dec.get("reason") == "regenerate" else "user")
    draft.update(cover_letter=after, version=draft.get("version", 1) + 1, word_count=len(after.split()),
                 edited_by_user=True)
    return {"draft": draft, "status": "compliance", "degraded": {"style_promoted": promoted} if promoted else {}}


@node("submit", timeout_s=60, retries=2)
async def submit(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    tid = config["configurable"]["thread_id"]
    payload = final_payload(state)
    draft = await d.port.create_proposal_draft("approval_gate", payload, _key(tid, "draft", payload))
    res = await d.port.submit_proposal("approval_gate", draft["proposal_id"], payload["job_id"], _key(tid, "submit"))
    if str(res.get("status", "")).startswith("rejected_by_platform"):
        return {"submission": res, "status": "needs_attention", "attention": f"Marketplace rejected: {res['status']}"}
    return {"submission": {**res, "proposal_id": draft["proposal_id"]}, "status": "submitted"}
