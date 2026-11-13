"""Background tasks (E1): scheduled scouting and long agent runs execute here, not inside web requests.

Idempotency: Arq job ids are deterministic (bid:<user>:<job>, resume:<thread>:<n>), the inbox records each job
once, graph threads are checkpointed in Postgres, and every marketplace write carries an idempotency key — so
a worker restart never double-analyses or double-submits.
"""

from __future__ import annotations

import logging

from agent import runtime
from agent.nodes.scout import scout_saved_search
from apps.api import db, services
from common.config import cfg

log = logging.getLogger("gigbid.worker")


async def analyse_job(ctx, user_id: str, job_id: str, run_id: str | None = None) -> dict:
    row = await db.fetchone("select status from inbox where user_id=%s and job_id=%s", user_id, job_id)
    if row and row["status"] not in ("queued", "degraded", "dead_letter", "failed"):
        return {"skipped": "already analysed", "status": row["status"]}
    return await services.execute("bid", user_id, runtime.bid_thread_id(user_id, job_id), inp={"job_id": job_id},
                                  run_id=run_id, job_id=job_id)


async def resume_bid(ctx, user_id: str, job_id: str, decision: dict, run_id: str | None = None) -> dict:
    return await services.execute("bid", user_id, runtime.bid_thread_id(user_id, job_id), resume=decision,
                                  run_id=run_id, job_id=job_id)


async def replay_bid(ctx, user_id: str, job_id: str, checkpoint_id: str, run_id: str | None = None) -> dict:
    return await services.execute("bid", user_id, runtime.bid_thread_id(user_id, job_id), run_id=run_id, job_id=job_id,
                                  checkpoint_id=checkpoint_id)


async def draft_reply(ctx, user_id: str, thread_id: str, run_id: str | None = None) -> dict:
    return await services.execute("conv", user_id, runtime.conv_thread_id(user_id, thread_id),
                                  inp={"thread_id": thread_id}, run_id=run_id)


async def resume_conv(ctx, user_id: str, thread_id: str, decision: dict, run_id: str | None = None) -> dict:
    return await services.execute("conv", user_id, runtime.conv_thread_id(user_id, thread_id), resume=decision,
                                  run_id=run_id)


async def scout(ctx, user_id: str, search_id: int | None = None) -> dict:
    """Run one user's due saved searches, de-duplicate and queue analysis of new jobs."""
    from agent.marketplace_port import make_port
    from agent.mcp_client import MarketplaceUnavailable, ToolBus

    u = await services.load_user(user_id)
    searches = await db.fetch("select * from saved_searches where user_id=%s and enabled and (%s::bigint is null or id=%s)",
                              user_id, search_id, search_id)
    seen = {r["fingerprint"] for r in await db.fetch("select fingerprint from seen_jobs where user_id=%s", user_id)}
    queued = 0
    try:
        async with ToolBus(user_id=user_id, tenant=u["tenant"], marketplace_token=await services.marketplace_token(user_id),
                           mode="http") as bus:
            port = make_port(bus)
            for s in searches:
                for j in await scout_saved_search(port, s, seen):
                    await db.execute("insert into seen_jobs(user_id,fingerprint,job_id) values (%s,%s,%s) on conflict do nothing",
                                     user_id, j["fingerprint"], j["job_id"])
                    await db.execute("insert into inbox(user_id,job_id,thread_id,title,category,connects,status) values "
                                     "(%s,%s,%s,%s,%s,%s,'queued') on conflict do nothing", user_id, j["job_id"],
                                     runtime.bid_thread_id(user_id, j["job_id"]), j["title"], j.get("category"),
                                     j.get("connects_cost"))
                    await services.enqueue("analyse_job", user_id=user_id, job_id=j["job_id"],
                                           _job_id=f"bid:{user_id}:{j['job_id']}")
                    queued += 1
                await db.execute("update saved_searches set last_run_at=now() where id=%s", s["id"])
    except MarketplaceUnavailable as e:
        log.warning("scout degraded for %s: %s", user_id, e)
        return {"degraded": str(e)}
    return {"queued": queued}


async def scout_due(ctx) -> dict:
    """Cron: run every saved search whose interval has elapsed (live mode never more often than configured)."""
    floor = cfg("marketplace", "live_min_poll_minutes" if cfg("marketplace", "mode") == "upwork" else "gigsim_poll_minutes")
    due = await db.fetch("select distinct user_id from saved_searches where enabled and (last_run_at is null or "
                         "last_run_at < now() - make_interval(mins => greatest(interval_minutes, %s)))", floor)
    for r in due:
        await services.enqueue("scout", user_id=r["user_id"], _job_id=f"scout:{r['user_id']}")
    return {"users": len(due)}


async def poll_events(ctx) -> dict:
    """Cron: marketplace events -> pipeline board, outcome memory, and reply drafts for new client messages."""
    from agent.marketplace_port import make_port
    from agent.mcp_client import MarketplaceUnavailable, ToolBus

    users = await db.fetch("select distinct user_id from pipeline")
    for r in users:
        uid = r["user_id"]
        u = await services.load_user(uid)
        cur = await db.fetchone("select last_seq from event_cursor where user_id=%s", uid)
        since = cur["last_seq"] if cur else 0
        try:
            async with runtime.persistence() as (_, store), ToolBus(user_id=uid, tenant=u["tenant"], mode="http",
                                                                     marketplace_token=await services.marketplace_token(uid)) as bus:
                evs = (await make_port(bus).list_events("pipeline", since)).get("events", [])
                threads = await services.apply_marketplace_events(uid, evs, store)
        except MarketplaceUnavailable:
            continue
        if evs:
            await db.execute("insert into event_cursor values (%s,%s) on conflict (user_id) do update set last_seq=excluded.last_seq",
                             uid, max(e["seq"] for e in evs))
        for t in threads:
            await services.enqueue("draft_reply", user_id=uid, thread_id=t, _job_id=f"conv:{uid}:{t}")
    return {"users": len(users)}
