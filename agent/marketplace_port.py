"""R1 — the single marketplace port. The graph only ever talks to `MarketplacePort`; `marketplace.mode` in
agent/config.yaml picks the adapter (GigSim via our Marketplace MCP server, or live Upwork via the official
Upwork MCP server). Nothing else in the graph changes when the mode changes."""

from __future__ import annotations

from typing import Any, Protocol

from common.config import cfg

from .mcp_client import ToolBus


class MarketplacePort(Protocol):
    mode: str

    async def search_jobs(self, agent: str, query: str = "", category: str = "", limit: int = 20, pool: str = "") -> dict: ...
    async def get_job(self, agent: str, job_id: str) -> dict: ...
    async def get_client_history(self, agent: str, client_id: str) -> dict: ...
    async def get_connects_balance(self, agent: str) -> dict: ...
    async def get_market_stats(self, agent: str, category: str) -> dict | None: ...
    async def get_policy(self, agent: str) -> dict: ...
    async def list_threads(self, agent: str) -> dict: ...
    async def list_messages(self, agent: str, thread_id: str) -> dict: ...
    async def list_events(self, agent: str, since: int = 0) -> dict: ...
    async def create_proposal_draft(self, agent: str, payload: dict, key: str, dry_run: bool = False) -> dict: ...
    async def submit_proposal(self, agent: str, proposal_id: str, job_id: str, key: str, dry_run: bool = False) -> dict: ...
    async def send_message(self, agent: str, thread_id: str, body: str, key: str, dry_run: bool = False) -> dict: ...


class GigSimPort:
    """GigSim adapter: every call goes through GigBid's Marketplace MCP server."""

    mode = "gigsim"

    def __init__(self, bus: ToolBus) -> None:
        self.bus = bus

    async def search_jobs(self, agent, query="", category="", limit=20, pool=""):
        return await self.bus.call(agent, "search_jobs", {"query": query, "category": category, "limit": limit, "pool": pool})

    async def get_job(self, agent, job_id):
        return await self.bus.call(agent, "get_job", {"job_id": job_id})

    async def get_client_history(self, agent, client_id):
        return await self.bus.call(agent, "get_client_history", {"client_id": client_id})

    async def get_connects_balance(self, agent):
        return await self.bus.call(agent, "get_connects_balance", {})

    async def get_market_stats(self, agent, category):
        return await self.bus.call(agent, "get_market_stats", {"category": category})

    async def get_policy(self, agent):
        return await self.bus.call(agent, "get_policy", {})

    async def list_threads(self, agent):
        return await self.bus.call(agent, "list_threads", {})

    async def list_messages(self, agent, thread_id):
        return await self.bus.call(agent, "list_messages", {"thread_id": thread_id})

    async def list_events(self, agent, since=0):
        return await self.bus.call(agent, "list_events", {"since": since})

    async def create_proposal_draft(self, agent, payload, key, dry_run=False):
        return await self.bus.call(agent, "create_proposal_draft", {**payload, "idempotency_key": key, "dry_run": dry_run})

    async def submit_proposal(self, agent, proposal_id, job_id, key, dry_run=False):
        return await self.bus.call(agent, "submit_proposal", {"proposal_id": proposal_id, "job_id": job_id,
                                                              "idempotency_key": key, "dry_run": dry_run})

    async def send_message(self, agent, thread_id, body, key, dry_run=False):
        return await self.bus.call(agent, "send_message", {"thread_id": thread_id, "body": body,
                                                           "idempotency_key": key, "dry_run": dry_run})


def make_port(bus: ToolBus, *, user_oauth: Any = None) -> MarketplacePort:
    mode = cfg("marketplace", "mode", default="gigsim")
    if mode == "upwork":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLivePort

        return UpworkLivePort(user_id=bus.user_id, oauth=user_oauth, allowlist_bus=bus)
    return GigSimPort(bus)
