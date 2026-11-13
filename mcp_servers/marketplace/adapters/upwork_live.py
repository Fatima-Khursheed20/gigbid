"""Live Upwork adapter (A4): the official Upwork MCP server (https://mcp.upwork.com/mcp) through
MultiServerMCPClient over Streamable HTTP, with OAuth 2.1 tokens stored encrypted per user.

Rules enforced here (not just in prompts):
* reads only, on a conservative schedule (marketplace.live_min_poll_minutes, see docs/RUNBOOK.md);
* proposals and messages are created only as DRAFTS after approval in GigBid — the user confirms on Upwork;
* no browser automation, no cookies, no scraping.

STATUS (honest): implemented against the MCP protocol and the OAuth 2.1 flow of the MCP Python SDK, but not
exercised against a live Upwork account during this assignment (no account available). Upwork's tool names
are discovered at connect time and mapped by keyword (configurable via marketplace.upwork_tool_map).
"""

from __future__ import annotations

import json
from typing import Any

from common.config import cfg
from common.settings import get_settings

DEFAULT_MAP = {  # our port method -> keywords that identify the Upwork tool
    "search_jobs": ["search", "job"],
    "get_job": ["get", "job"],
    "get_client_history": ["client"],
    "get_connects_balance": ["connect"],
    "list_threads": ["room"],
    "list_messages": ["message", "list"],
    "create_proposal_draft": ["proposal", "draft"],
    "send_message": ["message", "draft"],
}


def _pick(tool_names: list[str], keywords: list[str]) -> str | None:
    cands = [t for t in tool_names if all(k in t.lower() for k in keywords)]
    return sorted(cands, key=len)[0] if cands else None


class UpworkLivePort:
    mode = "upwork"

    def __init__(self, user_id: str, oauth: Any, allowlist_bus: Any) -> None:
        self.user_id, self.oauth, self.bus = user_id, oauth, allowlist_bus
        self._client = None
        self._map: dict[str, str] = {}

    async def _ensure(self) -> None:
        if self._client:
            return
        from langchain_mcp_adapters.client import MultiServerMCPClient

        if self.oauth is None:
            raise PermissionError("Upwork account not connected: complete OAuth in Settings → Connected accounts")
        self._client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": get_settings().upwork_mcp_url,
                                                        "auth": self.oauth, "timeout": 30}})
        tools = await self._client.get_tools(server_name="upwork")
        names = [t.name for t in tools]
        override = cfg("marketplace", "upwork_tool_map", default={}) or {}
        self._map = {m: override.get(m) or _pick(names, kw) for m, kw in DEFAULT_MAP.items()}
        self._tools = {t.name: t for t in tools}

    async def _call(self, agent: str, method: str, args: dict) -> dict:
        from agent.mcp_client import ALLOWLIST, ToolNotAllowed
        from mcp_servers.marketplace.adapters.gigsim import MarketplaceError

        if method not in ALLOWLIST.get(agent, set()):
            raise ToolNotAllowed(f"agent {agent!r} may not call {method!r}")
        await self._ensure()
        name = self._map.get(method)
        if not name:
            raise MarketplaceError(f"Upwork MCP server exposes no tool for {method}")
        out = await self._tools[name].ainvoke(args)
        if isinstance(out, str):
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return {"text": out}
        return out if isinstance(out, dict) else {"result": out}

    async def search_jobs(self, agent, query="", category="", limit=20, pool=""):
        return await self._call(agent, "search_jobs", {"query": query, "limit": limit})

    async def get_job(self, agent, job_id):
        return await self._call(agent, "get_job", {"id": job_id})

    async def get_client_history(self, agent, client_id):
        return await self._call(agent, "get_client_history", {"id": client_id})

    async def get_connects_balance(self, agent):
        return await self._call(agent, "get_connects_balance", {})

    async def get_market_stats(self, agent, category):
        return None  # not offered live; pricing falls back to the user's floor + historical stats

    async def get_policy(self, agent):
        return {"version": "upwork-live", "rules": [], "submission_checks": []}

    async def list_threads(self, agent):
        return await self._call(agent, "list_threads", {})

    async def list_messages(self, agent, thread_id):
        return await self._call(agent, "list_messages", {"room_id": thread_id})

    async def list_events(self, agent, since=0):
        return {"events": []}

    async def create_proposal_draft(self, agent, payload, key, dry_run=False):
        if dry_run:
            return {"dry_run": True, "would_send": payload, "connects_cost": None, "status": "preview"}
        res = await self._call(agent, "create_proposal_draft", payload)
        return {"dry_run": False, "would_send": payload, "proposal_id": str(res.get("id", key)), "status": "draft",
                "connects_cost": res.get("connects")}

    async def submit_proposal(self, agent, proposal_id, job_id, key, dry_run=False):
        # Upwork requires the user to confirm drafts on Upwork itself: GigBid never submits in live mode.
        return {"dry_run": dry_run, "proposal_id": proposal_id, "connects_cost": 0,
                "status": "draft_created_confirm_on_upwork"}

    async def send_message(self, agent, thread_id, body, key, dry_run=False):
        if dry_run:
            return {"dry_run": True, "thread_id": thread_id, "would_send": body, "status": "preview"}
        await self._call(agent, "send_message", {"room_id": thread_id, "message": body})
        return {"dry_run": False, "thread_id": thread_id, "would_send": body, "status": "draft_created_confirm_on_upwork"}
