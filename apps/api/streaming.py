"""SSE bridge to LangGraph runs: replays the stored execution trace, then streams live node events published
by the worker (Redis pub/sub) until the run ends. The user never stares at a spinner for a long run."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from . import db, services
from .auth.security import current_user

router = APIRouter(prefix="/api", tags=["runs"])
TERMINAL = {"done", "failed", "submitted", "skipped", "watch", "rejected", "awaiting_approval", "degraded",
            "dead_letter", "needs_attention", "blocked", "sent"}


@router.get("/runs/{run_id}/stream", operation_id="streamRun")
async def stream(run_id: str, request: Request, user=Depends(current_user)):  # noqa: B008
    run = await db.fetchone("select * from runs where id=%s and user_id=%s", run_id, user["id"])
    if not run:
        raise HTTPException(404, "run not found")

    async def gen():
        last_id = 0
        r = services.redis()
        pubsub = None
        if r:
            pubsub = r.pubsub()
            await pubsub.subscribe(f"run:{run_id}")
        try:
            for ev in await db.fetch("select id, data from run_events where run_id=%s order by id", run_id):
                last_id = ev["id"]
                yield {"event": "node", "data": json.dumps(ev["data"])}
            cur = await db.fetchone("select status from runs where id=%s", run_id)
            if cur and cur["status"] in TERMINAL:
                yield {"event": "end", "data": json.dumps({"status": cur["status"]})}
                return
            while not await request.is_disconnected():
                if pubsub:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg:
                        data = json.loads(msg["data"])
                        if data.get("kind") == "run_end":
                            yield {"event": "end", "data": json.dumps(data)}
                            return
                        yield {"event": "node", "data": msg["data"]}
                        continue
                else:  # no Redis: poll the trace table
                    await asyncio.sleep(1.0)
                    for ev in await db.fetch("select id, data from run_events where run_id=%s and id>%s order by id",
                                             run_id, last_id):
                        last_id = ev["id"]
                        yield {"event": "node", "data": json.dumps(ev["data"])}
                cur = await db.fetchone("select status from runs where id=%s", run_id)
                if cur and cur["status"] in TERMINAL:
                    yield {"event": "end", "data": json.dumps({"status": cur["status"]})}
                    return
                yield {"event": "ping", "data": "{}"}
        finally:
            if pubsub:
                await pubsub.unsubscribe()
                await pubsub.aclose()

    return EventSourceResponse(gen())
