"""Agent run viewer, checkpoint history and replay; pipeline, analytics, memory viewer and health."""

from __future__ import annotations

import os
import uuid

import httpx
from fastapi import APIRouter, HTTPException

from agent import runtime
from agent.graphs.bid_graph import build_bid_graph
from agent.memory.store import delete_memory, list_memory
from common import llm
from common.config import cfg
from common.settings import get_settings

from .. import db, services
from ..auth.security import CurrentUser
from ..schemas.models import (
    Analytics,
    Checkpoint,
    Health,
    MemoryOut,
    Ok,
    PipelineCard,
    Run,
    RunDetail,
    RunRef,
)

router = APIRouter(prefix="/api", tags=["runs"])


def _trace_url(r: dict) -> str | None:
    if os.environ.get("LANGSMITH_TRACING", "").lower() != "true" or not r.get("trace_id"):
        return None
    return f"https://smith.langchain.com/o/-/projects/p/{os.environ.get('LANGSMITH_PROJECT', 'gigbid')}?searchModel=" \
           f"%7B%22filter%22%3A%22has(metadata%2C%20%27%7B%5C%22trace_id%5C%22%3A%5C%22{r['trace_id']}%5C%22%7D%27)%22%7D"


def _run(r: dict) -> dict:
    return {**r, "started_at": str(r["started_at"]), "ended_at": str(r["ended_at"]) if r.get("ended_at") else None,
            "trace_url": _trace_url(r)}


@router.get("/runs", response_model=list[Run], operation_id="listRuns")
async def runs(limit: int = 50, user=CurrentUser) -> list[Run]:
    rows = await db.fetch("select * from runs where user_id=%s order by started_at desc limit %s", user["id"], min(limit, 200))
    return [Run(**_run(r)) for r in rows]


@router.get("/runs/{run_id}", response_model=RunDetail, operation_id="getRun")
async def run(run_id: str, user=CurrentUser) -> RunDetail:
    r = await db.fetchone("select * from runs where id=%s and user_id=%s", run_id, user["id"])
    if not r:
        raise HTTPException(404, "run not found")
    ev = await db.fetch("select data from run_events where run_id=%s order by id", run_id)
    return RunDetail(**_run(r), events=[e["data"] for e in ev])


@router.get("/jobs/{job_id}/history", response_model=list[Checkpoint], operation_id="checkpointHistory")
async def history(job_id: str, user=CurrentUser) -> list[Checkpoint]:
    """Checkpoint history of a job's thread: replay any job from any node (C6)."""
    out = []
    async with runtime.persistence() as (saver, store):
        g = build_bid_graph(saver, store)
        async for s in g.aget_state_history({"configurable": {"thread_id": runtime.bid_thread_id(user["id"], job_id)}}):
            out.append(Checkpoint(checkpoint_id=s.config["configurable"]["checkpoint_id"], next=list(s.next),
                                  step=(s.metadata or {}).get("step"), created_at=s.created_at,
                                  status=(s.values or {}).get("status")))
    return out


@router.post("/jobs/{job_id}/replay/{checkpoint_id}", response_model=RunRef, operation_id="replayFromCheckpoint")
async def replay(job_id: str, checkpoint_id: str, user=CurrentUser) -> RunRef:
    run_id = "run-" + uuid.uuid4().hex[:12]
    await db.execute("insert into runs(id,user_id,kind,thread_id,job_id,status) values (%s,%s,'bid',%s,%s,'queued')",
                     run_id, user["id"], runtime.bid_thread_id(user["id"], job_id), job_id)
    await services.enqueue("replay_bid", user_id=user["id"], job_id=job_id, checkpoint_id=checkpoint_id, run_id=run_id,
                           _job_id=f"replay:{run_id}")
    return RunRef(run_id=run_id)


@router.get("/pipeline", response_model=list[PipelineCard], operation_id="pipeline")
async def pipeline(user=CurrentUser) -> list[PipelineCard]:
    rows = await db.fetch("select * from pipeline where user_id=%s order by updated_at desc", user["id"])
    return [PipelineCard(**{**r, "updated_at": str(r["updated_at"])}) for r in rows]


@router.get("/analytics", response_model=Analytics, operation_id="analytics")
async def analytics(user=CurrentUser) -> Analytics:
    uid = user["id"]
    cats = await db.fetch(
        "select coalesce(category,'other') as category, count(*) filter (where stage<>'drafted') as submitted, "
        "count(*) filter (where stage in ('replied','interview','hired')) as replied, "
        "count(*) filter (where stage='hired') as hired from pipeline where user_id=%s group by 1", uid)
    for c in cats:
        c["reply_rate"] = round(c["replied"] / c["submitted"], 3) if c["submitted"] else None
        c["hire_rate"] = round(c["hired"] / c["submitted"], 3) if c["submitted"] else None
    con = await db.fetchone("select coalesce(sum(connects) filter (where stage<>'drafted'),0) as spent, "
                            "count(*) filter (where stage in ('replied','interview','hired')) as replies, "
                            "count(*) filter (where stage='hired') as hires from pipeline where user_id=%s", uid)
    con["connects_per_reply"] = round(con["spent"] / con["replies"], 2) if con["replies"] else None
    lat = await db.fetchone(
        "select count(*) as runs, percentile_cont(0.5) within group (order by latency_s) as p50, "
        "percentile_cont(0.95) within group (order by latency_s) as p95, avg(usd) as avg_usd, avg(tokens) as avg_tokens "
        "from runs where user_id=%s and latency_s is not null", uid)
    prop = await db.fetchone(
        "select count(*) as n, percentile_cont(0.95) within group (order by latency_s) as p95, avg(usd) as avg_usd "
        "from runs where user_id=%s and kind='bid' and status='awaiting_approval'", uid)
    rej = await db.fetch("select reason, count(*) as n from rejections where user_id=%s group by reason order by n desc limit 10", uid)
    funnel = await db.fetchone(
        "select count(*) as seen, count(*) filter (where action='bid') as recommended_bid, "
        "count(*) filter (where scam) as scams_flagged from inbox where user_id=%s", uid)
    stages = {r["stage"]: r["n"] for r in await db.fetch("select stage, count(*) as n from pipeline where user_id=%s group by stage", uid)}
    return Analytics(by_category=cats, connects=con,
                     cost_latency={"all_runs": lat, "proposal_runs": prop,
                                   "declared": cfg("budgets", "declared")},
                     rejection_reasons=rej, funnel={**{k: int(v or 0) for k, v in funnel.items()}, **stages})


@router.get("/memory", response_model=MemoryOut, operation_id="getMemory")
async def memory(user=CurrentUser) -> MemoryOut:
    async with runtime.persistence() as (_, store):
        m = await list_memory(store, user["id"])
    return MemoryOut(**m)


@router.delete("/memory/{kind}/{key}", response_model=Ok, operation_id="deleteMemory")
async def forget(kind: str, key: str, user=CurrentUser) -> Ok:
    if kind not in ("style", "outcome"):
        raise HTTPException(422, "kind must be style or outcome")
    async with runtime.persistence() as (_, store):
        await delete_memory(store, user["id"], kind, key)
    return Ok()


async def _probe(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(url)
        return "ok" if r.status_code < 400 else f"http {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return f"down ({type(e).__name__})"


@router.get("/health", response_model=Health, operation_id="health")
async def health() -> Health:
    s = get_settings()
    try:
        await db.fetch("select 1")
        dbs = "ok"
    except Exception as e:  # noqa: BLE001
        dbs = f"down ({type(e).__name__})"
    rs = "not configured"
    if r := services.redis():
        try:
            await r.ping()
            rs = "ok"
        except Exception as e:  # noqa: BLE001
            rs = f"down ({type(e).__name__})"
    mk = await _probe(s.mcp_marketplace_url.rsplit("/mcp", 1)[0] + "/health")
    if mk == "ok" and cfg("marketplace", "mode") == "gigsim":
        gs = await _probe(s.gigsim_base_url + "/health")
        mk = "ok" if gs == "ok" else f"gigsim {gs}"
    pf = await _probe(s.mcp_portfolio_url.rsplit("/mcp", 1)[0] + "/health")
    return Health(api="ok", db=dbs, redis=rs, marketplace=mk, portfolio=pf,
                  llm="ok" if llm.available() else "offline (heuristic fallbacks)",
                  marketplace_mode=cfg("marketplace", "mode"), model_profile=cfg("models", "profile"),
                  degraded=any(x != "ok" for x in (dbs, mk, pf)))
