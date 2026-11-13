"""Execution trace (kept apart from state and memory): every tool call and node observation of a run.

The API/worker installs a sink (DB writer + SSE publisher); offline runs just keep the list in memory.
"""

from __future__ import annotations

import contextvars
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from common.pii import mask_obj
from common.tracing import get_trace_id

Sink = Callable[[dict], Awaitable[None] | None]
_events: contextvars.ContextVar[list | None] = contextvars.ContextVar("trace_events", default=None)
_sink: contextvars.ContextVar[Sink | None] = contextvars.ContextVar("trace_sink", default=None)


def start(sink: Sink | None = None) -> list:
    ev: list = []
    _events.set(ev)
    _sink.set(sink)
    return ev


def _summ(v: Any, limit: int = 600) -> Any:
    try:
        s = json.dumps(v, default=str)
    except Exception:  # noqa: BLE001
        s = str(v)
    return json.loads(s) if len(s) <= limit else {"summary": s[:limit] + "…"}


async def record(kind: str, node: str, **data: Any) -> None:
    ev = {"ts": time.time(), "kind": kind, "node": node, "trace_id": get_trace_id(),
          **{k: _summ(mask_obj(v)) for k, v in data.items()}}
    lst = _events.get()
    if lst is not None:
        lst.append(ev)
    sink = _sink.get()
    if sink:
        r = sink(ev)
        if hasattr(r, "__await__"):
            await r
