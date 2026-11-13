"""Conversation graph (C1): one thread per client conversation.

load_thread -> classify intent (question | negotiation | interview_request | scam_signal) -> [find_slots] ->
draft_reply -> msg_compliance -> msg_approval (interrupt) -> approve: msg_send | edit: msg_apply_edit -> ... |
reject: END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..nodes.liaison import (
    classify,
    draft_reply,
    find_slots,
    load_thread,
    msg_apply_edit,
    msg_approval,
    msg_compliance,
    msg_send,
)
from ..state import ConvState

HALT = {"degraded", "dead_letter", "needs_attention", "blocked"}


def _go(nxt: str):
    def route(state: dict) -> str:
        return END if state.get("status") in HALT else nxt
    return route


def after_classify(state: dict) -> str:
    if state.get("status") in HALT:
        return END
    return "find_slots" if state["intent"]["intent"] == "interview_request" else "draft_reply"


def after_approval(state: dict) -> str:
    return {"approve": "msg_send", "edit": "msg_apply_edit", "reject": END}[state["approval"]["action"]]


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConvState)
    for name, fn in [("load_thread", load_thread), ("classify", classify), ("find_slots", find_slots),
                     ("draft_reply", draft_reply), ("msg_compliance", msg_compliance), ("msg_approval", msg_approval),
                     ("msg_apply_edit", msg_apply_edit), ("msg_send", msg_send)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_thread")
    g.add_conditional_edges("load_thread", _go("classify"), ["classify", END])
    g.add_conditional_edges("classify", after_classify, ["find_slots", "draft_reply", END])
    g.add_conditional_edges("find_slots", _go("draft_reply"), ["draft_reply", END])
    g.add_conditional_edges("draft_reply", _go("msg_compliance"), ["msg_compliance", END])
    g.add_conditional_edges("msg_compliance", _go("msg_approval"), ["msg_approval", END])
    g.add_conditional_edges("msg_approval", after_approval, ["msg_send", "msg_apply_edit", END])
    g.add_edge("msg_apply_edit", "msg_compliance")
    g.add_edge("msg_send", END)
    return g.compile(checkpointer=checkpointer, store=store, name="conversation_graph")
