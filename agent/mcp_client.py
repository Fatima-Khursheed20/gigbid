"""MCP client setup + per-agent tool allowlists (A6).

Agents never call GigSim, Upwork, the database or files directly: every capability is an MCP tool.
`ToolBus` opens MCP sessions for one run (MultiServerMCPClient over streamable HTTP in production, in-memory
sessions in tests/offline evals), enforces each agent's allowlist, applies timeouts + bounded retries, records
every call in the execution trace and turns transport failures into a typed degraded state.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from common.settings import get_settings
from common.tracing import TRACE_HEADER, get_trace_id

from . import tracebus

ALLOWLIST: dict[str, set[str]] = {
    "scout": {"search_jobs", "get_job"},
    "risk_assessor": {"get_client_history"},
    "fit_matcher": {"requirement_matrix", "search_evidence", "list_skills"},
    "pricing": {"get_market_stats", "get_connects_balance", "get_policy"},
    "writer": {"search_evidence", "get_case_study"},
    "critic": {"search_evidence"},
    "liaison": {"list_threads", "list_messages", "search_evidence", "free_slots"},
    "approval_gate": {"create_proposal_draft", "submit_proposal", "get_connects_balance"},  # dry_run preview + submit
    "conv_gate": {"send_message", "create_interview_hold", "create_email_draft"},
    "pipeline": {"list_events", "list_proposals", "list_threads"},
    "baseline": {"search_jobs", "get_job", "get_client_history", "get_market_stats", "get_connects_balance",
                 "search_evidence", "requirement_matrix", "get_case_study", "create_proposal_draft"},
}

SERVER_OF: dict[str, str] = {
    **dict.fromkeys(["search_evidence", "requirement_matrix", "get_case_study", "list_skills"], "portfolio"),
    **dict.fromkeys(["search_jobs", "get_job", "get_client_history", "get_connects_balance", "get_market_stats",
                     "get_policy", "list_threads", "list_messages", "list_events", "list_proposals",
                     "create_proposal_draft", "submit_proposal", "send_message"], "marketplace"),
    **dict.fromkeys(["free_slots", "create_interview_hold", "create_email_draft", "list_holds"], "workspace"),
}

TIMEOUT_S = {"portfolio": 60.0, "marketplace": 30.0, "workspace": 15.0}


class ToolNotAllowed(PermissionError):
    pass


class ToolError(RuntimeError):
    pass


class MarketplaceUnavailable(RuntimeError):
    """Raised when the marketplace MCP server (or GigSim behind it) cannot be reached: the UI shows a degraded
    banner, the run is queued and the worker retries later (A6)."""


TRANSIENT_MARKERS = ("unreachable", "HTTP 503", "HTTP 502", "HTTP 500", "rate limit", "HTTP 429", "unavailable")


class ToolBus:
    def __init__(self, *, user_id: str, tenant: str, marketplace_token: str | None = None, mode: str = "http") -> None:
        self.user_id, self.tenant, self.mode = user_id, tenant, mode
        self.marketplace_token = marketplace_token or f"gs-{user_id}"
        self._stack = contextlib.AsyncExitStack()
        self._sessions: dict[str, Any] = {}
        self._client = None

    def headers(self) -> dict[str, str]:
        s = get_settings()
        return {"X-Tenant-Id": self.tenant, "X-User-Id": self.user_id, "X-Marketplace-Token": self.marketplace_token,
                TRACE_HEADER: get_trace_id(), "Authorization": f"Bearer {s.mcp_marketplace_token}"}

    async def __aenter__(self) -> ToolBus:
        if self.mode == "http":
            from langchain_mcp_adapters.client import MultiServerMCPClient

            s = get_settings()
            h = self.headers()
            self._client = MultiServerMCPClient({
                "portfolio": {"transport": "streamable_http", "url": s.mcp_portfolio_url, "headers": h, "timeout": 60},
                "marketplace": {"transport": "streamable_http", "url": s.mcp_marketplace_url, "headers": h, "timeout": 30},
                "workspace": {"transport": "streamable_http", "url": s.mcp_workspace_url, "headers": h, "timeout": 15},
            })
        else:
            from mcp_servers.common import REQUEST_DEFAULTS

            REQUEST_DEFAULTS.set({k: v for k, v in self.headers().items()})
        return self

    async def __aexit__(self, *exc) -> None:
        with contextlib.suppress(Exception):
            await self._stack.aclose()
        self._sessions.clear()

    async def _session(self, server: str):
        if server in self._sessions:
            return self._sessions[server]
        if self.mode == "http":
            sess = await self._stack.enter_async_context(self._client.session(server))
        else:
            from mcp.shared.memory import create_connected_server_and_client_session

            mod = {"portfolio": "mcp_servers.portfolio.server", "marketplace": "mcp_servers.marketplace.server",
                   "workspace": "mcp_servers.workspace.server"}[server]
            srv = __import__(mod, fromlist=["mcp"]).mcp
            sess = await self._stack.enter_async_context(create_connected_server_and_client_session(srv))
        self._sessions[server] = sess
        return sess

    async def call(self, agent: str, tool: str, args: dict | None = None, *, retries: int = 2) -> dict:
        if tool not in ALLOWLIST.get(agent, set()):
            await tracebus.record("tool_denied", agent, tool=tool)
            raise ToolNotAllowed(f"agent {agent!r} may not call {tool!r}")
        server = SERVER_OF[tool]
        args = args or {}
        last: Exception | None = None
        for attempt in range(retries + 1):
            t0 = time.perf_counter()
            try:
                sess = await asyncio.wait_for(self._session(server), timeout=TIMEOUT_S[server])
                res = await asyncio.wait_for(sess.call_tool(tool, args), timeout=TIMEOUT_S[server])
            except (TimeoutError, OSError, ConnectionError) as e:
                last = e
                self._sessions.pop(server, None)
            except Exception as e:  # noqa: BLE001 - httpx/anyio transport errors surface in many types
                last = e
                self._sessions.pop(server, None)
            else:
                ms = round((time.perf_counter() - t0) * 1000)
                text = " ".join(getattr(c, "text", "") for c in (res.content or []))
                if res.isError:
                    await tracebus.record("tool_error", agent, tool=tool, args=args, error=text[:300], ms=ms)
                    if server == "marketplace" and any(m in text for m in TRANSIENT_MARKERS):
                        last = MarketplaceUnavailable(text[:200])
                        if attempt < retries:
                            await asyncio.sleep(0.5 * 2 ** attempt)
                            continue
                        raise last
                    raise ToolError(f"{tool}: {text[:300]}")
                out = res.structuredContent
                if out is None:
                    try:
                        out = json.loads(text)
                    except json.JSONDecodeError:
                        out = {"text": text}
                if isinstance(out, dict) and set(out) == {"result"}:
                    out = out["result"]
                await tracebus.record("tool_call", agent, tool=tool, args=args, result=out, ms=ms)
                return out
            if attempt < retries:
                await asyncio.sleep(0.5 * 2 ** attempt)
        await tracebus.record("tool_unreachable", agent, tool=tool, error=str(last)[:200])
        if server == "marketplace":
            raise MarketplaceUnavailable(f"marketplace MCP server unreachable: {type(last).__name__}")
        raise ToolError(f"{server} MCP server unreachable: {last}")

    async def langchain_tools(self, agent: str) -> list:
        """LangChain tools for tool-calling agents (baselines), filtered by the agent's allowlist."""
        from langchain_mcp_adapters.tools import load_mcp_tools

        tools = []
        for server in {"portfolio", "marketplace", "workspace"}:
            sess = await self._session(server)
            tools += [t for t in await load_mcp_tools(sess) if t.name in ALLOWLIST[agent]]
        return tools
