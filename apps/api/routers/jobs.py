"""Job inbox, job detail, proposal studio (approvals) and paragraph regeneration."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException

from agent import runtime
from agent.graphs.bid_graph import build_bid_graph
from common import llm
from common.config import prompt

from .. import db, services
from ..auth.security import CurrentUser
from ..schemas.models import Decision, InboxItem, JobDetail, Ok, RegenerateIn, RegenerateOut, RunRef, Studio

router = APIRouter(prefix="/api", tags=["jobs"])


async def bid_state(user_id: str, job_id: str):
    async with runtime.persistence() as (saver, store):
        g = build_bid_graph(saver, store)
        return await g.aget_state({"configurable": {"thread_id": runtime.bid_thread_id(user_id, job_id)}})


def _pending(snap) -> dict | None:
    ints = [i.value for t in snap.tasks for i in (t.interrupts or [])]
    return ints[0] if ints else None


@router.get("/jobs", response_model=list[InboxItem], operation_id="listInbox")
async def inbox(action: str | None = None, status: str | None = None, user=CurrentUser) -> list[InboxItem]:
    rows = await db.fetch("select * from inbox where user_id=%s and (%s::text is null or action=%s) and "
                          "(%s::text is null or status=%s) order by (action='bid') desc, fit desc nulls last, updated_at desc "
                          "limit 300", user["id"], action, action, status, status)
    return [InboxItem(**{**r, "updated_at": str(r["updated_at"])}) for r in rows]


@router.post("/jobs/scout", response_model=RunRef, operation_id="scoutNow")
async def scout_now(user=CurrentUser) -> RunRef:
    if not await db.fetchone("select 1 as x from saved_searches where user_id=%s", user["id"]):
        raise HTTPException(400, "add a saved search first")
    jid = await services.enqueue("scout", user_id=user["id"], _job_id=f"scout:{user['id']}:{uuid.uuid4().hex[:6]}")
    return RunRef(run_id=jid, status="queued")


@router.post("/jobs/{job_id}/analyze", response_model=RunRef, operation_id="analyzeJob")
async def analyze(job_id: str, user=CurrentUser) -> RunRef:
    run_id = "run-" + uuid.uuid4().hex[:12]
    await db.execute("insert into inbox(user_id,job_id,thread_id,title,status) values (%s,%s,%s,%s,'queued') "
                     "on conflict (user_id,job_id) do update set status='queued'", user["id"], job_id,
                     runtime.bid_thread_id(user["id"], job_id), job_id)
    await db.execute("insert into runs(id,user_id,kind,thread_id,job_id,status) values (%s,%s,'bid',%s,%s,'queued')",
                     run_id, user["id"], runtime.bid_thread_id(user["id"], job_id), job_id)
    await services.enqueue("analyse_job", user_id=user["id"], job_id=job_id, run_id=run_id, _job_id=f"bid:{user['id']}:{job_id}:{run_id}")
    return RunRef(run_id=run_id)


@router.post("/jobs/{job_id}/skip", response_model=Ok, operation_id="skipJob")
async def skip(job_id: str, user=CurrentUser) -> Ok:
    await db.execute("update inbox set status='skipped_by_user', action='skip' where user_id=%s and job_id=%s", user["id"], job_id)
    return Ok()


@router.get("/jobs/{job_id}", response_model=JobDetail, operation_id="getJob")
async def job_detail(job_id: str, user=CurrentUser) -> JobDetail:
    snap = await bid_state(user["id"], job_id)
    v = snap.values or {}
    if not v.get("job"):
        raise HTTPException(404, "job not analysed yet")
    return JobDetail(job=v["job"], status=v.get("status"), job_spec=v.get("job_spec"), risk=v.get("risk"), fit=v.get("fit"),
                     decision=v.get("decision"), price=v.get("price"), client=v.get("client"),
                     thread_id=runtime.bid_thread_id(user["id"], job_id), has_pending_approval=_pending(snap) is not None,
                     attention=v.get("attention"), degraded=v.get("degraded"))


@router.get("/approvals", response_model=list[InboxItem], operation_id="listApprovals")
async def approvals(user=CurrentUser) -> list[InboxItem]:
    rows = await db.fetch("select * from inbox where user_id=%s and status='awaiting_approval' order by updated_at desc", user["id"])
    return [InboxItem(**{**r, "updated_at": str(r["updated_at"])}) for r in rows]


@router.get("/proposals/{job_id}", response_model=Studio, operation_id="getStudio")
async def studio(job_id: str, user=CurrentUser) -> Studio:
    """The pending approval lives in the Postgres checkpoint, so a refresh (or an API restart) never loses it."""
    snap = await bid_state(user["id"], job_id)
    v = snap.values or {}
    return Studio(job_id=job_id, thread_id=runtime.bid_thread_id(user["id"], job_id), pending=_pending(snap) is not None,
                  status=v.get("status"), payload=_pending(snap), submission=v.get("submission"),
                  history=v.get("approvals", []))


@router.post("/proposals/{job_id}/decision", response_model=RunRef, operation_id="decideProposal")
async def decide(job_id: str, body: Decision, user=CurrentUser) -> RunRef:
    snap = await bid_state(user["id"], job_id)
    if _pending(snap) is None:
        raise HTTPException(409, "no pending approval for this job")
    if body.action == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "edited_text required for edit")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required when rejecting")
    n = len((snap.values or {}).get("approvals", []))
    run_id = "run-" + uuid.uuid4().hex[:12]
    await db.execute("update inbox set status=%s where user_id=%s and job_id=%s",
                     {"approve": "submitting", "edit": "rechecking", "reject": "rejecting"}[body.action], user["id"], job_id)
    await db.execute("insert into runs(id,user_id,kind,thread_id,job_id,status) values (%s,%s,'bid',%s,%s,'queued')",
                     run_id, user["id"], runtime.bid_thread_id(user["id"], job_id), job_id)
    await services.enqueue("resume_bid", user_id=user["id"], job_id=job_id,
                           decision={**body.model_dump(), "user_id": user["id"]}, run_id=run_id,
                           _job_id=f"resume:{user['id']}:{job_id}:{n}")
    return RunRef(run_id=run_id)


@router.post("/proposals/{job_id}/regenerate", response_model=RegenerateOut, operation_id="regenerateParagraph")
async def regenerate(job_id: str, body: RegenerateIn, user=CurrentUser) -> RegenerateOut:
    """Rewrite ONE paragraph using only the evidence the writer saw. Not a user edit: never feeds style memory."""
    snap = await bid_state(user["id"], job_id)
    p = _pending(snap)
    if not p:
        raise HTTPException(409, "no pending draft")
    paras = [x for x in re.split(r"\n\s*\n", p["draft"]["cover_letter"]) if x.strip()]
    if body.paragraph_index >= len(paras):
        raise HTTPException(422, "no such paragraph")
    ev = p.get("evidence", [])
    if llm.available():
        ev_txt = "\n".join(f"[E{i + 1}] ({e.get('project')}) {e.get('text', '')[:500]}" for i, e in enumerate(ev))
        new = await llm.complete("writer", prompt("writer"),
                                 f"EVIDENCE:\n{ev_txt}\n\nFULL DRAFT:\n{p['draft']['cover_letter']}\n\nRewrite ONLY paragraph "
                                 f"{body.paragraph_index + 1} (shown below). {body.instruction}\nReturn the paragraph text only, "
                                 f"keeping [E<n>] citations.\n\nPARAGRAPH:\n{paras[body.paragraph_index]}", max_tokens=400)
        new = new.strip().strip('"')
    else:
        new = paras[body.paragraph_index]
    paras[body.paragraph_index] = new
    return RegenerateOut(paragraph=new, cover_letter="\n\n".join(paras))
