"""Client threads with suggested replies and interview slots; approve before sending."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from agent import runtime
from agent.graphs.conversation_graph import build_conversation_graph
from agent.marketplace_port import make_port
from agent.mcp_client import MarketplaceUnavailable, ToolBus

from .. import db, services
from ..auth.security import CurrentUser
from ..schemas.models import Decision, RunRef, Thread, ThreadDetail

router = APIRouter(prefix="/api/messages", tags=["messages"])


async def conv_state(user_id: str, thread_id: str):
    async with runtime.persistence() as (saver, store):
        g = build_conversation_graph(saver, store)
        return await g.aget_state({"configurable": {"thread_id": runtime.conv_thread_id(user_id, thread_id)}})


async def _port_call(user, fn):
    try:
        async with ToolBus(user_id=user["id"], tenant=user["tenant"], mode="http",
                           marketplace_token=await services.marketplace_token(user["id"])) as bus:
            return await fn(make_port(bus))
    except MarketplaceUnavailable as e:
        raise HTTPException(503, f"marketplace unavailable: {e}") from e


@router.get("/threads", response_model=list[Thread], operation_id="listThreads")
async def threads(user=CurrentUser) -> list[Thread]:
    res = await _port_call(user, lambda p: p.list_threads("liaison"))
    local = {r["thread_id"]: r for r in await db.fetch("select * from conv_threads where user_id=%s", user["id"])}
    out = []
    for t in res.get("threads", []):
        loc = local.get(t["id"], {})
        out.append(Thread(thread_id=t["id"], job_id=t.get("job_id"), n=t.get("n"), status=loc.get("status"),
                          intent=loc.get("intent"), last_message=loc.get("last_message")))
    return out


@router.get("/threads/{thread_id}", response_model=ThreadDetail, operation_id="getThread")
async def thread(thread_id: str, user=CurrentUser) -> ThreadDetail:
    msgs = await _port_call(user, lambda p: p.list_messages("liaison", thread_id))
    snap = await conv_state(user["id"], thread_id)
    ints = [i.value for t in snap.tasks for i in (t.interrupts or [])]
    return ThreadDetail(thread_id=thread_id, messages=msgs.get("messages", []), pending=bool(ints),
                        payload=ints[0] if ints else None, status=(snap.values or {}).get("status"))


@router.post("/threads/{thread_id}/draft", response_model=RunRef, operation_id="draftReply")
async def draft(thread_id: str, user=CurrentUser) -> RunRef:
    run_id = "run-" + uuid.uuid4().hex[:12]
    await db.execute("insert into runs(id,user_id,kind,thread_id,status) values (%s,%s,'conv',%s,'queued')", run_id,
                     user["id"], runtime.conv_thread_id(user["id"], thread_id))
    await services.enqueue("draft_reply", user_id=user["id"], thread_id=thread_id, run_id=run_id,
                           _job_id=f"conv:{user['id']}:{thread_id}:{run_id}")
    return RunRef(run_id=run_id)


@router.post("/threads/{thread_id}/decision", response_model=RunRef, operation_id="decideReply")
async def decide(thread_id: str, body: Decision, user=CurrentUser) -> RunRef:
    snap = await conv_state(user["id"], thread_id)
    if not any(t.interrupts for t in snap.tasks):
        raise HTTPException(409, "no pending reply for this thread")
    run_id = "run-" + uuid.uuid4().hex[:12]
    n = len((snap.values or {}).get("approvals", []))
    await db.execute("insert into runs(id,user_id,kind,thread_id,status) values (%s,%s,'conv',%s,'queued')", run_id,
                     user["id"], runtime.conv_thread_id(user["id"], thread_id))
    await services.enqueue("resume_conv", user_id=user["id"], thread_id=thread_id, decision=body.model_dump(),
                           run_id=run_id, _job_id=f"resume-conv:{user['id']}:{thread_id}:{n}")
    return RunRef(run_id=run_id)
