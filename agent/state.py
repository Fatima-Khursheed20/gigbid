"""Typed graph state + reducers (C2).

Three things are kept apart:
* STATE (this module): what one job / conversation needs right now. Small, checkpointed by Postgres.
* EXECUTION TRACE: every tool name, argument, result and observation -> `run_events` table + LangSmith,
  written by agent/tracebus.py, never stored in state.
* LONG-TERM MEMORY: only promoted knowledge, in the LangGraph store (agent/memory/), written by explicit rules.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


def keep_last(_: Any, b: Any) -> Any:
    return b


class BidState(TypedDict, total=False):
    # identity (set at start)
    user_id: str
    tenant: str
    job_id: str
    trace_id: str
    autonomy: str
    # inputs (job post is UNTRUSTED data)
    job: dict
    client: dict
    # parallel analyses — each branch writes its own key; shared keys use reducers
    job_spec: dict
    risk: dict
    fit: dict
    analyses_done: Annotated[list[str], operator.add]
    # decision & bid
    decision: dict
    price: dict
    policy: dict
    evidence: list[dict]
    draft: dict
    verification: dict
    critiques: Annotated[list[dict], operator.add]
    revisions: int
    compliance: dict
    preview: dict
    approval: dict
    approvals: Annotated[list[dict], operator.add]
    submission: dict
    # bookkeeping
    status: str
    attention: str | None
    errors: Annotated[list[str], operator.add]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    usd: Annotated[float, operator.add]
    degraded: Annotated[dict, merge_dict]


class ConvState(TypedDict, total=False):
    user_id: str
    tenant: str
    thread_id: str
    job_id: str | None
    trace_id: str
    messages: list[dict]
    last_client_message: dict
    intent: dict
    slots: list[dict]
    reply: dict
    compliance: dict
    approval: dict
    approvals: Annotated[list[dict], operator.add]
    sent: dict
    status: str
    attention: str | None
    errors: Annotated[list[str], operator.add]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    usd: Annotated[float, operator.add]
