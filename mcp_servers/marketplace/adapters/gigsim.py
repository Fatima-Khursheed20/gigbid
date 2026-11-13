"""GigSim REST adapter used by the Marketplace MCP server: timeouts, bounded retries with backoff that honour
Retry-After, and typed errors so callers can show a degraded state instead of crashing (A6, C7)."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from common.config import cfg
from common.tracing import TRACE_HEADER, get_trace_id

log = logging.getLogger("gigbid.gigsim")


class MarketplaceError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status, self.detail = status, detail


class MarketplaceUnavailable(MarketplaceError):
    """GigSim down, timing out, or rate-limited past our retry budget."""


class PolicyViolation(MarketplaceError):
    pass


class GigSimAdapter:
    def __init__(self, base_url: str, token: str, client: httpx.AsyncClient | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.token = token
        self.client = client or httpx.AsyncClient(timeout=cfg("marketplace", "request_timeout_s", default=15))

    async def _req(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None,
                   idem: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}", TRACE_HEADER: get_trace_id()}
        if idem:
            headers["Idempotency-Key"] = idem
        retries = int(cfg("marketplace", "max_retries", default=3))
        base = float(cfg("marketplace", "backoff_base_s", default=0.8))
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = await self.client.request(method, self.base + path, params=params, json=json, headers=headers)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                last = MarketplaceUnavailable(f"GigSim unreachable: {type(e).__name__}")
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    ra = r.headers.get("Retry-After")
                    last = MarketplaceUnavailable(f"GigSim HTTP {r.status_code}", r.status_code, r.text[:200])
                    if attempt < retries:
                        wait = min(float(ra), 20.0) if (ra and ra.isdigit()) else base * (2 ** attempt)
                        await asyncio.sleep(wait + random.uniform(0, 0.2))
                        continue
                    raise last
                if r.status_code == 422:
                    detail = r.json().get("detail")
                    if isinstance(detail, dict) and detail.get("error") == "policy_violation":
                        raise PolicyViolation("platform policy violation", 422, detail)
                    raise MarketplaceError("invalid request", 422, detail)
                if r.status_code >= 400:
                    raise MarketplaceError(f"GigSim HTTP {r.status_code}", r.status_code, r.text[:300])
                return r.json()
            if attempt < retries:
                await asyncio.sleep(base * (2 ** attempt) + random.uniform(0, 0.2))
        raise last or MarketplaceUnavailable("GigSim unavailable")

    # ---- reads
    async def search_jobs(self, query: str = "", category: str = "", limit: int = 20, pool: str = "") -> dict:
        return await self._req("GET", "/v1/jobs", params={"q": query, "category": category, "limit": limit, "pool": pool})

    async def get_job(self, job_id: str) -> dict:
        return await self._req("GET", f"/v1/jobs/{job_id}")

    async def get_client_history(self, client_id: str) -> dict:
        return await self._req("GET", f"/v1/clients/{client_id}")

    async def get_connects_balance(self) -> dict:
        return await self._req("GET", "/v1/connects")

    async def get_market_stats(self, category: str) -> dict:
        return await self._req("GET", "/v1/market/stats", params={"category": category})

    async def get_policy(self) -> dict:
        return await self._req("GET", "/v1/policy")

    async def list_threads(self) -> dict:
        return await self._req("GET", "/v1/threads")

    async def list_messages(self, thread_id: str) -> dict:
        return await self._req("GET", f"/v1/threads/{thread_id}/messages")

    async def list_events(self, since: int = 0) -> dict:
        return await self._req("GET", "/v1/events", params={"since": since})

    async def list_proposals(self) -> dict:
        return await self._req("GET", "/v1/proposals")

    # ---- writes (always with an idempotency key)
    async def create_proposal_draft(self, payload: dict, idem: str) -> dict:
        return await self._req("POST", "/v1/proposals", json=payload, idem=idem)

    async def submit_proposal(self, proposal_id: str, idem: str) -> dict:
        return await self._req("POST", f"/v1/proposals/{proposal_id}/submit", idem=idem)

    async def send_message(self, thread_id: str, body: str, idem: str) -> dict:
        return await self._req("POST", f"/v1/threads/{thread_id}/messages", json={"body": body}, idem=idem)
