"""Node plumbing shared by both graphs: runtime dependencies, budgets (C4), timeouts/retries/dead-letter (C7),
per-node token/cost accounting (R8) and execution-trace events."""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from common.config import cfg
from common.llm import Ledger, LLMUnavailable, _ledger

from .. import tracebus
from ..mcp_client import MarketplaceUnavailable, ToolBus

log = logging.getLogger("gigbid.nodes")


@dataclass
class UserProfile:
    user_id: str
    tenant: str
    name: str = "Freelancer"
    hourly_rate: float = 35.0
    floor_rate: float = 20.0
    min_project: float = 200.0
    weekly_connects_budget: int = 80
    autonomy: str = "suggest"
    categories: list[str] = field(default_factory=list)
    voice: str = ""  # writing voice (agency mode: drafts in the routed member's voice)


@dataclass
class Deps:
    bus: ToolBus
    port: Any
    store: Any  # LangGraph BaseStore (long-term memory)
    profile: UserProfile
    ledger: Ledger = field(default_factory=Ledger)


def deps(config) -> Deps:
    return config["configurable"]["deps"]


class Budget(RuntimeError):
    pass


def over_budget(state: dict) -> str | None:
    if state.get("steps", 0) >= cfg("budgets", "max_graph_steps", default=40):
        return "step budget exceeded"
    if state.get("tokens", 0) >= cfg("budgets", "max_tokens_per_job", default=30000):
        return "token budget exceeded"
    return None


def node(name: str, timeout_s: float = 120.0, retries: int = 1):
    """Wrap a node: budget check, timeout, bounded retry, degraded/dead-letter mapping, accounting, trace."""

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(state: dict, config: RunnableConfig) -> dict:
            if reason := over_budget(state):
                await tracebus.record("budget", name, reason=reason)
                return {"status": "needs_attention", "attention": reason, "steps": 1}
            d = deps(config)
            local = Ledger()
            token = _ledger.set(local)
            t0 = time.perf_counter()
            await tracebus.record("node_start", name)
            out: dict | None = None
            err: str | None = None
            try:
                for attempt in range(retries + 1):
                    try:
                        out = await asyncio.wait_for(fn(state, config), timeout=timeout_s)
                        break
                    except GraphInterrupt:
                        raise
                    except MarketplaceUnavailable as e:
                        out = {"status": "degraded", "degraded": {name: str(e)[:200]},
                               "errors": [f"{name}: marketplace unavailable"]}
                        break
                    except (TimeoutError, LLMUnavailable) as e:
                        err = f"{name}: {type(e).__name__}: {str(e)[:160]}"
                        if attempt < retries:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                    except Exception as e:  # noqa: BLE001
                        err = f"{name}: {type(e).__name__}: {str(e)[:200]}"
                        log.exception("node %s failed", name)
                        if attempt < retries:
                            continue
                if out is None:
                    out = {"status": "dead_letter", "errors": [err or f"{name}: failed"], "attention": err}
            finally:
                _ledger.reset(token)
                for c in local.calls:
                    d.ledger.add(c)
            dt = time.perf_counter() - t0
            out = dict(out)
            out["steps"] = 1
            out["tokens"] = sum(c.input_tokens + c.output_tokens for c in local.calls)
            out["usd"] = round(sum(c.usd for c in local.calls), 7)
            await tracebus.record("node_end", name, latency_s=round(dt, 3), tokens=out["tokens"], usd=out["usd"],
                                  status=out.get("status"), llm_calls=len(local.calls),
                                  models=sorted({c.model for c in local.calls}))
            return out

        wrapper.node_name = name
        return wrapper

    return deco
