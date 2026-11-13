"""One trace id flows from the UI request through the API, the graph, every MCP server and the audit log (E3)."""

from __future__ import annotations

import contextvars
import logging
import uuid

TRACE_HEADER = "X-Trace-Id"
_trace: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(tid: str | None) -> str:
    tid = tid or new_trace_id()
    _trace.set(tid)
    return tid


def get_trace_id() -> str:
    return _trace.get()


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


def langsmith_url(run_id: str | None) -> str | None:
    """Best-effort link to the LangSmith trace for a graph run."""
    import os

    if not run_id or os.environ.get("LANGSMITH_TRACING", "").lower() != "true":
        return None
    project = os.environ.get("LANGSMITH_PROJECT", "gigbid")
    return f"https://smith.langchain.com/o/-/projects/p/{project}/r/{run_id}"
