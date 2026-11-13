"""Runtime glue shared by the API, the worker, the tests and the evals: persistence (Postgres checkpointer +
store, or in-memory), dependency wiring, and run/resume helpers that stream node events."""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from langgraph.types import Command

from common.llm import Ledger
from common.settings import get_settings
from common.tracing import set_trace_id

from . import tracebus
from .graphs.bid_graph import build_bid_graph
from .graphs.conversation_graph import build_conversation_graph
from .marketplace_port import make_port
from .mcp_client import ToolBus
from .nodes._base import Deps, UserProfile


@contextlib.asynccontextmanager
async def persistence(dsn: str | None = None) -> AsyncIterator[tuple[Any, Any]]:
    """Postgres checkpointer + store when DATABASE_URL is set (durable approvals, C6), else in-memory."""
    dsn = dsn if dsn is not None else get_settings().database_url
    if dsn:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore

        async with AsyncPostgresSaver.from_conn_string(dsn) as saver, AsyncPostgresStore.from_conn_string(dsn) as store:
            await saver.setup()
            await store.setup()
            yield saver, store
    else:

        yield _MEM["saver"], _MEM["store"]


def _mem():
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    return {"saver": InMemorySaver(), "store": InMemoryStore()}


_MEM = _mem()


def reset_memory() -> None:
    global _MEM
    _MEM = _mem()


def bid_thread_id(user_id: str, job_id: str) -> str:
    return f"bid:{user_id}:{job_id}"


def conv_thread_id(user_id: str, thread_id: str) -> str:
    return f"conv:{user_id}:{thread_id}"


async def run_graph(kind: str, *, profile: UserProfile, thread_id: str, inp: dict | None = None,
                    resume: dict | None = None, mode: str = "http", marketplace_token: str | None = None,
                    on_event: Callable[[dict], Any] | None = None, checkpoint_id: str | None = None,
                    dsn: str | None = None) -> dict:
    """Run (or resume) one graph thread to its next stop: END or an interrupt. Returns a summary dict."""
    trace = set_trace_id(uuid.uuid4().hex)
    events = tracebus.start(on_event)
    ledger = Ledger()
    t0 = time.perf_counter()
    async with persistence(dsn) as (saver, store), ToolBus(user_id=profile.user_id, tenant=profile.tenant,
                                                            marketplace_token=marketplace_token, mode=mode) as bus:
        graph = (build_bid_graph if kind == "bid" else build_conversation_graph)(saver, store)
        deps = Deps(bus=bus, port=make_port(bus), store=store, profile=profile, ledger=ledger)
        cfg = {"configurable": {"thread_id": thread_id, "deps": deps},
               "metadata": {"user_id": profile.user_id, "trace_id": trace, "kind": kind},
               "run_name": f"{kind}_graph", "tags": [kind, profile.tenant], "recursion_limit": 60}
        if checkpoint_id:
            cfg["configurable"]["checkpoint_id"] = checkpoint_id
        payload: Any = Command(resume=resume) if resume is not None else (inp if inp is not None else None)
        async for chunk in graph.astream(payload, cfg, stream_mode="updates"):
            for node_name, update in chunk.items():
                if node_name == "__interrupt__":
                    continue
                await tracebus.record("update", node_name, keys=sorted((update or {}).keys()),
                                      status=(update or {}).get("status"))
        snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    interrupts = [i.value for t in snap.tasks for i in (t.interrupts or [])]
    return {"thread_id": thread_id, "trace_id": trace, "state": snap.values, "interrupt": interrupts[0] if interrupts else None,
            "next": list(snap.next), "events": events, "latency_s": round(time.perf_counter() - t0, 3),
            "tokens": ledger.tokens, "usd": ledger.usd, "by_node": ledger.by_node(), "llm_calls": ledger.to_list()}
