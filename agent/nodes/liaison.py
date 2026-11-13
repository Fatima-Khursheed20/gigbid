"""Client Liaison nodes for the conversation graph: read new messages, classify intent, draft a reply or
interview slots, compliance, dry-run preview, interrupt for approval, send exactly once."""

from __future__ import annotations

import hashlib
import re

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from common import llm
from common.config import prompt

from ..guards import delimit, detect_injection, neutralise
from ..handoffs import ApprovalDecision, MessageIntent, ReplyDraft
from ..memory.promotion_rules import record_edit
from ._base import deps, node
from .compliance import check_text

SCAM = re.compile(r"(?i)whatsapp|telegram|crypto|usdt|western union|onboarding kit|outside the platform|password|login")
INTERVIEW = re.compile(r"(?i)\b(call|interview|meet|chat|slots?|times? work)\b")
NEGOTIATE = re.compile(r"(?i)\b(budget|lower|discount|cheaper|rate of|could you do it for)\b")


def heuristic_intent(text: str) -> MessageIntent:
    inj = bool(detect_injection(text)) or bool(re.search(r"(?i)ignore (all )?your previous instructions", text))
    if SCAM.search(text):
        it = "scam_signal"
    elif INTERVIEW.search(text):
        it = "interview_request"
    elif NEGOTIATE.search(text):
        it = "negotiation"
    elif "?" in text:
        it = "question"
    else:
        it = "other"
    return MessageIntent(intent=it, injection_detected=inj, summary=text[:140])


@node("load_thread", timeout_s=40)
async def load_thread(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    res = await d.port.list_messages("liaison", state["thread_id"])
    msgs = res.get("messages", [])
    last = next((m for m in reversed(msgs) if m.get("sender") == "client"), None)
    return {"messages": msgs, "last_client_message": last or {}, "status": "classifying"}


@node("classify", timeout_s=40)
async def classify(state: dict, config: RunnableConfig) -> dict:
    text = (state.get("last_client_message") or {}).get("body", "")
    rules = heuristic_intent(text)
    intent = rules
    if llm.available():
        try:
            intent = await llm.structured("intent", prompt("intent"), delimit(text, "client_message"), MessageIntent,
                                          max_tokens=300)
            if rules.intent == "scam_signal":
                intent.intent = "scam_signal"  # rules are a floor, as in the Risk Assessor
            intent.injection_detected = intent.injection_detected or rules.injection_detected
        except Exception:  # noqa: BLE001
            intent = rules
    return {"intent": intent.model_dump(), "status": "drafting"}


@node("find_slots", timeout_s=30)
async def find_slots(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    res = await d.bus.call("liaison", "free_slots", {"days": 5, "duration_minutes": 30, "max_slots": 3})
    return {"slots": res.get("slots", [])}


def _template_reply(intent: str, slots: list[dict], floor: float) -> str:
    if intent == "scam_signal":
        return ("Thanks for getting back to me. I keep all communication and payments on the platform, so let's "
                "continue here. Happy to answer any questions about the project in this thread.")
    if intent == "interview_request":
        s = "; ".join(f"{x['start'][:16].replace('T', ' ')}" for x in slots) or "any weekday afternoon"
        return f"Thanks, I'd be glad to talk. These times work for me (PKT): {s}. Let me know which suits you."
    if intent == "negotiation":
        return (f"Thanks for being upfront about the budget. I can't go below ${floor:.0f}/h, but I can reduce scope "
                "to fit: for example we start with the core feature and add the rest in a second milestone.")
    return "Thanks for the question. Short answer: yes, I've done closely related work; happy to walk you through it here."


@node("draft_reply", timeout_s=120)
async def draft_reply(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    msg = (state.get("last_client_message") or {}).get("body", "")
    intent = state["intent"]["intent"]
    slots = state.get("slots", [])
    ev: list[dict] = []
    if intent == "question":
        clean, _ = neutralise(msg)
        res = await d.bus.call("liaison", "search_evidence", {"requirement": clean[:500], "k": 3})
        ev = res.get("items", [])
    body = _template_reply(intent, slots, d.profile.floor_rate)
    ids = [e["evidence_id"] for e in ev]
    if llm.available():
        ev_txt = "\n".join(f"[E{i + 1}] ({e.get('project')}) {e.get('text', '')[:500]}" for i, e in enumerate(ev))
        user = (f"intent: {intent}\nfreelancer floor rate: ${d.profile.floor_rate}/h\nslots: "
                f"{[s['start'] for s in slots]}\nEVIDENCE:\n{ev_txt or '(none)'}\n\n" + delimit(neutralise(msg)[0], "client_message"))
        try:
            r = await llm.structured("liaison", prompt("liaison"), user, ReplyDraft, max_tokens=500)
            body, ids = r.body, [ev[int(m) - 1]["evidence_id"] for m in re.findall(r"\[E(\d+)\]", r.body) if 0 < int(m) <= len(ev)]
        except Exception:  # noqa: BLE001
            pass
    reply = ReplyDraft(body=body, proposed_slots=slots if intent == "interview_request" else [], evidence_ids=ids)
    return {"reply": reply.model_dump(), "status": "compliance"}


@node("msg_compliance", timeout_s=30)
async def msg_compliance(state: dict, config: RunnableConfig) -> dict:
    reply = dict(state["reply"])
    v = check_text(re.sub(r"\s?\[E\d+\]", "", reply["body"]), {"submission_checks": []})
    reply["body"] = v.cleaned_text
    return {"reply": reply, "compliance": v.model_dump(), "status": "blocked" if v.blocked and len(reply["body"]) < 10
            else "awaiting_approval"}


@node("msg_approval", timeout_s=10_000_000, retries=0)
async def msg_approval(state: dict, config: RunnableConfig) -> dict:
    decision = interrupt({"type": "message_approval", "thread_id": state["thread_id"], "messages": state.get("messages", []),
                          "intent": state.get("intent"), "reply": state["reply"], "compliance": state.get("compliance"),
                          "preview": {"would_send": state["reply"]["body"], "cost": "free (messages cost no Connects)"}})
    dec = ApprovalDecision.model_validate(decision)
    return {"approval": dec.model_dump(), "approvals": [dec.model_dump()],
            "status": {"approve": "sending", "edit": "editing", "reject": "rejected"}[dec.action]}


@node("msg_apply_edit", timeout_s=30)
async def msg_apply_edit(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    reply = dict(state["reply"])
    after = state["approval"].get("edited_text") or reply["body"]
    await record_edit(d.store, d.profile.user_id, state["thread_id"], reply["body"], after)
    reply["body"] = after
    return {"reply": reply, "status": "compliance"}


@node("msg_send", timeout_s=60, retries=2)
async def msg_send(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    body = state["reply"]["body"]
    key = f"{config['configurable']['thread_id']}:msg:{hashlib.sha1(body.encode()).hexdigest()[:10]}"
    res = await d.port.send_message("conv_gate", state["thread_id"], body, key)
    holds = []
    for s in state["reply"].get("proposed_slots", [])[:3]:
        h = await d.bus.call("conv_gate", "create_interview_hold", {"start": s["start"], "duration_minutes": 30,
                                                                     "title": f"Interview hold ({state['thread_id']})",
                                                                     "idempotency_key": f"{key}:{s['start']}"})
        holds.append(h)
    return {"sent": {**res, "holds": holds}, "status": "sent"}
