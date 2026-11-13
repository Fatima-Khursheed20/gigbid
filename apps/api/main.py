"""GigBid API (FastAPI). Serves /api/* and, in production, the built web app.

    uvicorn apps.api.main:app --port 8000
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from common.pii import setup_logging
from common.settings import get_settings
from common.tracing import TRACE_HEADER, set_trace_id

from . import db
from .routers import auth, jobs, messages, runs
from .streaming import router as stream_router

log = logging.getLogger("gigbid.api")


async def seed_reviewer() -> None:
    """Reviewer login preloaded with a persona (E6). Credentials come only from environment variables."""
    s = get_settings()
    if not (s.reviewer_email and s.reviewer_password):
        return
    from .auth.security import create_user, hash_pw

    u = await db.fetchone("select id from users where email=%s", s.reviewer_email.lower())
    uid = u["id"] if u else await create_user(s.reviewer_email, s.reviewer_password, "Reviewer", is_reviewer=True)
    await db.execute("update users set password_hash=%s, is_reviewer=true where id=%s", hash_pw(s.reviewer_password), uid)
    await db.execute("update profiles set tenant='ai_ml', persona='ai_ml', hourly_rate=45, floor_rate=30, min_project=300, "
                     "categories=%s, onboarded=true where user_id=%s", json.dumps(["ai_ml"]), uid)
    if not await db.fetchone("select 1 as x from saved_searches where user_id=%s", uid):
        await db.execute("insert into saved_searches(user_id,name,query,category,pool,interval_minutes) values "
                         "(%s,'AI/ML jobs (live stream)','', 'ai_ml','stream',30), (%s,'AI/ML dev pool','', 'ai_ml','dev',60)", uid, uid)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    if get_settings().database_url:
        await db.migrate()
        await auth.restore_uploads()
        await seed_reviewer()
    yield
    await db.close()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan,
              description="Multi-agent freelancer copilot: job inbox, grounded proposals, approvals, conversations.")


@app.middleware("http")
async def trace_mw(request: Request, call_next):
    tid = set_trace_id(request.headers.get(TRACE_HEADER))
    resp = await call_next(request)
    resp.headers[TRACE_HEADER] = tid
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "internal error", "type": type(exc).__name__}, status_code=500)


for r in (auth.router, jobs.router, messages.router, runs.router, stream_router):
    app.include_router(r)

DIST = Path(get_settings().web_dist)
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
