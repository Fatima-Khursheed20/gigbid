"""Bid graph (C1): one thread per job. Hand-written StateGraph.

intake -> {analyst | risk | matcher} in parallel (Send) -> decide -> skip/watch END | bid -> pricing -> writer ->
verifier -> critic -> (revise -> writer, at most twice) -> compliance -> (blocked END) -> prepare_preview ->
human_approval (interrupt) -> approve: submit | edit: apply_edit -> compliance ... | reject: END
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from common.config import cfg

from ..nodes._base import node
from ..nodes.analyst import analyst
from ..nodes.approval import apply_edit, human_approval, prepare_preview, submit
from ..nodes.compliance import compliance
from ..nodes.critic import critic
from ..nodes.decide import decide
from ..nodes.fit_matcher import fit_matcher
from ..nodes.pricing import pricing
from ..nodes.risk_assessor import risk_assessor
from ..nodes.scout import intake
from ..nodes.verifier import verifier
from ..nodes.writer import writer
from ..state import BidState

HALT = {"degraded", "dead_letter", "needs_attention", "blocked"}


def go(nxt: str):
    def route(state: dict) -> str:
        return END if state.get("status") in HALT else nxt
    route.__name__ = f"to_{nxt}"
    return route


def fan_out(state: dict):
    if state.get("status") in HALT:
        return END
    return [Send("analyst", state), Send("risk", state), Send("matcher", state)]


def after_decide(state: dict) -> str:
    if state.get("status") in HALT:
        return END
    return "pricing" if state["decision"]["action"] == "bid" else END


def after_critic(state: dict) -> str:
    if state.get("status") in HALT:
        return END
    last = state["critiques"][-1]
    if last["approve"] or state.get("revisions", 0) >= cfg("budgets", "max_revisions", default=2):
        return "compliance"
    return "revise"


@node("revise", timeout_s=5)
async def revise(state: dict, config: RunnableConfig) -> dict:
    return {"revisions": state.get("revisions", 0) + 1, "status": "revising"}


def after_compliance(state: dict) -> str:
    return END if state.get("status") in HALT else "prepare_preview"


def after_approval(state: dict) -> str:
    a = state["approval"]["action"]
    return {"approve": "submit", "edit": "apply_edit", "reject": END}[a]


def build_bid_graph(checkpointer=None, store=None):
    g = StateGraph(BidState)
    g.add_node("intake", intake)
    g.add_node("analyst", analyst)
    g.add_node("risk", risk_assessor)
    g.add_node("matcher", fit_matcher)
    g.add_node("decide", decide)
    g.add_node("pricing", pricing)
    g.add_node("writer", writer)
    g.add_node("verifier", verifier)
    g.add_node("critic", critic)
    g.add_node("revise", revise)
    g.add_node("compliance", compliance)
    g.add_node("prepare_preview", prepare_preview)
    g.add_node("human_approval", human_approval)
    g.add_node("apply_edit", apply_edit)
    g.add_node("submit", submit)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk", "matcher", END])
    g.add_edge(["analyst", "risk", "matcher"], "decide")
    g.add_conditional_edges("decide", after_decide, ["pricing", END])
    g.add_conditional_edges("pricing", go("writer"), ["writer", END])
    g.add_conditional_edges("writer", go("verifier"), ["verifier", END])
    g.add_conditional_edges("verifier", go("critic"), ["critic", END])
    g.add_conditional_edges("critic", after_critic, ["compliance", "revise", END])
    g.add_edge("revise", "writer")
    g.add_conditional_edges("compliance", after_compliance, ["prepare_preview", END])
    g.add_conditional_edges("prepare_preview", go("human_approval"), ["human_approval", END])
    g.add_conditional_edges("human_approval", after_approval, ["submit", "apply_edit", END])
    g.add_edge("apply_edit", "compliance")
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer, store=store, name="bid_graph")
