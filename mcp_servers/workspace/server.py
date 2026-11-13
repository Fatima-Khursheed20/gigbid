"""GigBid Workspace MCP server (A3): free calendar slots, tentative interview holds, email drafts.

Backed by a local mock (SQLite) with a seeded busy calendar — documented in docs/TOOLS.md. The agent only
sees MCP tools, so swapping in Google Calendar/Gmail later changes this file, not the graph.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import threading
from typing import Annotated
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from common.config import cfg
from common.settings import ROOT
from mcp_servers.common import header, http_app, trace_from, transport_security

mcp = FastMCP("gigbid-workspace", transport_security=transport_security(), instructions="Calendar availability, tentative interview holds and email drafts "
                                                "for the freelancer. Holds and drafts are never sent automatically.")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class Slot(BaseModel):
    start: str
    end: str


class Slots(BaseModel):
    timezone: str
    slots: list[Slot]


class Hold(BaseModel):
    hold_id: str
    start: str
    end: str
    title: str
    status: str


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str


class _DB:
    def __init__(self) -> None:
        path = os.environ.get("WORKSPACE_DB", str(ROOT / "data" / "processed" / "workspace.db"))
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript("""create table if not exists holds (id text primary key, user_id text, start text, end_ text,
            title text, status text); create table if not exists drafts (id text primary key, user_id text, to_ text,
            subject text, body text, status text)""")

    def q(self, sql, args=()):
        with self.lock:
            r = self.db.execute(sql, args).fetchall()
            self.db.commit()
            return r


DB = _DB()


def _tz() -> ZoneInfo:
    return ZoneInfo(cfg("workspace", "timezone", default="UTC"))


def _busy(user: str, day: dt.date) -> list[tuple[dt.datetime, dt.datetime]]:
    """Deterministic seeded busy blocks per user/day plus existing holds."""
    tz = _tz()
    h = int(hashlib.md5(f"{user}{day}".encode()).hexdigest(), 16)
    blocks = []
    for i in range(2):
        start_h = 10 + (h >> (i * 4)) % 7
        s = dt.datetime.combine(day, dt.time(start_h, 0), tz)
        blocks.append((s, s + dt.timedelta(minutes=60)))
    for (start, end_) in DB.q("select start, end_ from holds where user_id=? and status='tentative'", (user,)):
        s, e = dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end_)
        if s.date() == day:
            blocks.append((s, e))
    return blocks


def _user(ctx) -> str:
    trace_from(ctx)
    return header(ctx, "X-User-Id") or "local"


@mcp.tool(annotations=READ, title="Free calendar slots")
def free_slots(
    days: Annotated[int, Field(ge=1, le=14, description="How many working days ahead to search")] = 5,
    duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30,
    max_slots: Annotated[int, Field(ge=1, le=10)] = 3,
    start_date: Annotated[str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    ctx: Context | None = None,
) -> Slots:
    """Free interview slots within working hours, spread across different days."""
    user = _user(ctx)
    tz = _tz()
    wh = cfg("workspace", "working_hours", default=[10, 18])
    day = dt.date.fromisoformat(start_date) if start_date else (dt.datetime.now(tz) + dt.timedelta(days=1)).date()
    out: list[Slot] = []
    scanned = 0
    while len(out) < max_slots and scanned < days + 7:
        if day.weekday() < 5:
            busy = _busy(user, day)
            t = dt.datetime.combine(day, dt.time(wh[0], 0), tz)
            end_day = dt.datetime.combine(day, dt.time(wh[1], 0), tz)
            while t + dt.timedelta(minutes=duration_minutes) <= end_day:
                e = t + dt.timedelta(minutes=duration_minutes)
                if all(e <= bs or t >= be for bs, be in busy):
                    out.append(Slot(start=t.isoformat(), end=e.isoformat()))
                    break  # one slot per day: give the client a spread of days
                t += dt.timedelta(minutes=cfg("workspace", "slot_minutes", default=30))
            scanned += 1
        day += dt.timedelta(days=1)
    return Slots(timezone=str(tz), slots=out)


@mcp.tool(annotations=WRITE, title="Create tentative interview hold")
def create_interview_hold(
    start: Annotated[str, Field(description="ISO-8601 start time")],
    duration_minutes: Annotated[int, Field(ge=15, le=120)],
    title: Annotated[str, Field(min_length=3, max_length=120)],
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
    ctx: Context | None = None,
) -> Hold:
    """Block a tentative slot on the freelancer's own calendar (nothing is sent to the client)."""
    user = _user(ctx)
    s = dt.datetime.fromisoformat(start)
    e = s + dt.timedelta(minutes=duration_minutes)
    hid = "hold-" + hashlib.sha1(f"{user}|{idempotency_key}".encode()).hexdigest()[:10]
    DB.q("insert or ignore into holds values(?,?,?,?,?,?)", (hid, user, s.isoformat(), e.isoformat(), title, "tentative"))
    return Hold(hold_id=hid, start=s.isoformat(), end=e.isoformat(), title=title, status="tentative")


@mcp.tool(annotations=WRITE, title="Create email draft")
def create_email_draft(
    to: Annotated[str, Field(min_length=3, max_length=200)],
    subject: Annotated[str, Field(min_length=1, max_length=200)],
    body: Annotated[str, Field(min_length=1, max_length=5000)],
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
    ctx: Context | None = None,
) -> EmailDraft:
    """Save an email draft in the freelancer's mailbox (never sent automatically)."""
    user = _user(ctx)
    did = "draft-" + hashlib.sha1(f"{user}|{idempotency_key}".encode()).hexdigest()[:10]
    DB.q("insert or ignore into drafts values(?,?,?,?,?,?)", (did, user, to, subject, body, "draft"))
    return EmailDraft(draft_id=did, to=to, subject=subject, body=body, status="draft")


@mcp.tool(annotations=READ, title="List holds")
def list_holds(ctx: Context | None = None) -> dict:
    """Tentative interview holds on the calendar."""
    user = _user(ctx)
    rows = DB.q("select id, start, end_, title, status from holds where user_id=? order by start", (user,))
    return {"holds": [dict(zip(["hold_id", "start", "end", "title", "status"], r, strict=True)) for r in rows]}


def create_app():
    return http_app(mcp, "WORKSPACE_MCP_TOKEN")


if __name__ == "__main__":
    print(json.dumps([t.name for t in mcp._tool_manager.list_tools()]))
