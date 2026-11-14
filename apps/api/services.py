"""Run orchestration shared by the API and the worker: start/resume graph threads, persist the execution trace,
publish live events for SSE, and project graph state into the inbox / pipeline / analytics tables."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import redis.asyncio as aioredis

from agent import runtime
from agent.memory.promotion_rules import record_outcome
from agent.nodes._base import UserProfile
from common.settings import get_settings

from . import db
from .auth import token_store

log = logging.getLogger("gigbid.services")
_redis: aioredis.Redis | None = None


def redis() -> aioredis.Redis | None:
    global _redis
    url = get_settings().redis_url
    if not url:
        return None
    if _redis is None:
        _redis = aioredis.from_url(url, decode_responses=True)
    return _redis


def _voice(tenant: str) -> str:
    from common.settings import ROOT

    for base in ("tenants", "personas"):
        p = ROOT / "data" / base / tenant / "profile.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("voice", "")
    return ""


def profile_of(u: dict) -> UserProfile:
    return UserProfile(voice=_voice(u.get("tenant") or "ai_ml"), user_id=u["id"] if "id" in u else u["user_id"], tenant=u.get("tenant") or u.get("persona") or "ai_ml",
                       name=u.get("name", "Freelancer"), hourly_rate=u.get("hourly_rate") or 35,
                       floor_rate=u.get("floor_rate") or 20, min_project=u.get("min_project") or 200,
                       weekly_connects_budget=u.get("weekly_connects_budget") or 80, autonomy=u.get("autonomy") or "suggest",
                       categories=u.get("categories") or [])


async def load_user(user_id: str) -> dict:
    u = await db.fetchone("select u.id, u.email, u.name, p.* from users u join profiles p on p.user_id=u.id where u.id=%s",
                          user_id)
    if not u:
        raise KeyError(user_id)
    return u


async def marketplace_token(user_id: str) -> str:
    t = await token_store.get(user_id, "gigsim")
    return (t or {}).get("token") or f"gs-{user_id}"


def _sink(run_id: str):
    r = redis()

    async def sink(ev: dict) -> None:
        await db.execute("insert into run_events(run_id, ts, kind, node, data) values (%s,%s,%s,%s,%s)",
                         run_id, ev["ts"], ev["kind"], ev.get("node"), db.j(ev))
        if r:
            await r.publish(f"run:{run_id}", json.dumps(ev, default=str))
    return sink


async def _end(run_id: str, payload: dict) -> None:
    if r := redis():
        await r.publish(f"run:{run_id}", json.dumps({"kind": "run_end", **payload}, default=str))


async def execute(kind: str, user_id: str, thread_id: str, *, inp: dict | None = None, resume: dict | None = None,
                  run_id: str | None = None, job_id: str | None = None, checkpoint_id: str | None = None) -> dict:
    run_id = run_id or "run-" + uuid.uuid4().hex[:12]
    u = await load_user(user_id)
    prof = profile_of(u)
    await db.execute("insert into runs(id,user_id,kind,thread_id,job_id,status) values (%s,%s,%s,%s,%s,'running') "
                     "on conflict (id) do update set status='running'", run_id, user_id, kind, thread_id, job_id)
    try:
        res = await runtime.run_graph(kind, profile=prof, thread_id=thread_id, inp=inp, resume=resume, mode="http",
                                      marketplace_token=await marketplace_token(user_id), on_event=_sink(run_id),
                                      checkpoint_id=checkpoint_id)
    except Exception as e:  # noqa: BLE001 - recorded as a failed run, surfaced in the run viewer
        log.exception("run %s failed", run_id)
        await db.execute("update runs set status='failed', ended_at=now(), error=%s where id=%s", str(e)[:500], run_id)
        await _end(run_id, {"status": "failed", "error": str(e)[:300]})
        raise
    st = res["state"]
    status = "awaiting_approval" if res["interrupt"] else st.get("status", "done")
    await db.execute("update runs set status=%s, ended_at=now(), latency_s=%s, tokens=%s, usd=%s, by_node=%s, trace_id=%s "
                     "where id=%s", status, res["latency_s"], res["tokens"], res["usd"], db.j(res["by_node"]),
                     res["trace_id"], run_id)
    if kind == "bid":
        await project_bid(user_id, thread_id, st, status)
    else:
        await project_conv(user_id, st, status)
    await _end(run_id, {"status": status, "interrupt": bool(res["interrupt"])})
    return {"run_id": run_id, "status": status, "interrupt": res["interrupt"]}


async def project_bid(user_id: str, thread_id: str, st: dict, status: str) -> None:
    job = st.get("job") or {}
    if not job:
        return
    dec, fit, risk, price = st.get("decision") or {}, st.get("fit") or {}, st.get("risk") or {}, st.get("price") or {}
    summary = {"reasons": dec.get("reasons", []), "flags": risk.get("flags", []), "attention": st.get("attention"),
               "degraded": st.get("degraded")}
    await db.execute(
        "insert into inbox(user_id,job_id,thread_id,title,category,fit,risk,scam,injection,action,price,bid_type,connects,status,summary,updated_at) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) on conflict (user_id,job_id) do update set "
        "fit=excluded.fit, risk=excluded.risk, scam=excluded.scam, injection=excluded.injection, action=excluded.action, "
        "price=excluded.price, bid_type=excluded.bid_type, connects=excluded.connects, status=excluded.status, "
        "summary=excluded.summary, updated_at=now()",
        user_id, job["job_id"], thread_id, job.get("title", ""), job.get("category"), fit.get("score"), risk.get("score"),
        risk.get("scam"), risk.get("injection_detected"), dec.get("action"), price.get("amount"), price.get("bid_type"),
        job.get("connects_cost"), status, db.j(summary))
    if status == "awaiting_approval":
        await db.execute("insert into pipeline(user_id,proposal_id,job_id,thread_id,stage,category,title,amount,connects) "
                         "values (%s,%s,%s,%s,'drafted',%s,%s,%s,%s) on conflict (user_id,proposal_id) do update set "
                         "stage='drafted', amount=excluded.amount, updated_at=now()",
                         user_id, f"draft:{job['job_id']}", job["job_id"], thread_id, job.get("category"), job.get("title"),
                         price.get("amount"), job.get("connects_cost"))
    if status == "rejected":
        await db.execute("insert into rejections(user_id,job_id,reason) values (%s,%s,%s)", user_id, job["job_id"],
                         (st.get("approval") or {}).get("reason") or "no reason")
        await db.execute("delete from pipeline where user_id=%s and proposal_id=%s", user_id, f"draft:{job['job_id']}")
    if status == "submitted":
        sub = st.get("submission") or {}
        cited = sorted({e.get("project_id") for e in st.get("evidence", []) if e.get("project_id")})
        await db.execute("delete from pipeline where user_id=%s and proposal_id=%s", user_id, f"draft:{job['job_id']}")
        await db.execute("insert into pipeline(user_id,proposal_id,job_id,thread_id,stage,category,title,amount,connects,cited_projects) "
                         "values (%s,%s,%s,%s,'submitted',%s,%s,%s,%s,%s) on conflict (user_id,proposal_id) do nothing",
                         user_id, sub.get("proposal_id"), job["job_id"], thread_id, job.get("category"), job.get("title"),
                         price.get("amount"), sub.get("connects_cost"), db.j(cited))


async def project_conv(user_id: str, st: dict, status: str) -> None:
    if not st.get("thread_id"):
        return
    await db.execute("insert into conv_threads(user_id,thread_id,status,intent,last_message,updated_at) values "
                     "(%s,%s,%s,%s,%s,now()) on conflict (user_id,thread_id) do update set status=excluded.status, "
                     "intent=excluded.intent, last_message=excluded.last_message, updated_at=now()",
                     user_id, st["thread_id"], status, (st.get("intent") or {}).get("intent"),
                     (st.get("last_client_message") or {}).get("body"))


STAGE_ORDER = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


async def apply_marketplace_events(user_id: str, events: list[dict], store: Any) -> list[str]:
    """Pipeline board + outcome memory from marketplace events. Returns thread ids that need a reply draft."""
    replies = []
    for ev in events:
        row = await db.fetchone("select * from pipeline where user_id=%s and proposal_id=%s", user_id, ev["proposal_id"])
        if not row:
            continue
        if STAGE_ORDER.index(ev["type"]) > STAGE_ORDER.index(row["stage"]) or ev["type"] == "lost":
            await db.execute("update pipeline set stage=%s, updated_at=now(), thread_id=coalesce(%s, thread_id) "
                             "where user_id=%s and proposal_id=%s", ev["type"], ev.get("thread_id"), user_id, ev["proposal_id"])
        await record_outcome(store, user_id, row["category"] or "other", ev["type"], row["cited_projects"] or [])
        if ev["type"] == "replied" and ev.get("thread_id"):
            replies.append(ev["thread_id"])
    return replies


async def enqueue(fn: str, **kwargs: Any) -> str:
    """Queue background work on the Arq worker (never inside the web request). Deterministic job ids make
    re-enqueues idempotent."""
    from arq import create_pool
    from arq.connections import RedisSettings

    job_id = kwargs.pop("_job_id", None)
    url = get_settings().redis_url
    if not url:  # dev fallback without Redis: run in-process in the background
        import asyncio

        from worker import tasks

        asyncio.create_task(getattr(tasks, fn)({}, **kwargs))
        return job_id or fn
    pool = await create_pool(RedisSettings.from_dsn(url))
    try:
        job = await pool.enqueue_job(fn, _job_id=job_id, **kwargs)
        return job.job_id if job else (job_id or "duplicate")
    finally:
        await pool.aclose()


def now() -> float:
    return time.time()
