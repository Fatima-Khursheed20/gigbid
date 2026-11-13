"""GigSim — marketplace simulator (GigBid's stand-in for the instructor-provided simulator).

REST API with: jobs (dev pool + a live stream released over simulated time, incl. duplicates, scams and
planted prompt injections), clients with histories, Connects, proposals (draft -> submit), messages,
pipeline events, per-token rate limits (HTTP 429) and occasional injected 5xx errors.

Run:  uvicorn gigsim.app:app --port 8081
Env:  GIGSIM_DB (sqlite path), GIGSIM_RATE_LIMIT_PER_MIN (60), GIGSIM_ERROR_RATE (0.03),
      GIGSIM_POLICY_VERSION (v1|v2), GIGSIM_ADMIN_TOKEN, GIGSIM_TOKEN_PREFIX (gs-),
      GIGSIM_INCLUDE_HELDOUT (0|1), GIGSIM_SPEED (simulated minutes per real second, default 2)
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import client_model

HERE = Path(__file__).resolve().parent
SEED = HERE / "seed"
ROOT = HERE.parent


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class World:
    """Static seed data loaded once."""

    def __init__(self) -> None:
        self.policy_all = json.loads((SEED / "policy.json").read_text(encoding="utf-8"))
        self.clients = {c["client_id"]: c for c in json.loads((SEED / "clients.json").read_text(encoding="utf-8"))}
        jobs = json.loads((SEED / "dev_jobs.json").read_text(encoding="utf-8"))
        self.stream = json.loads((SEED / "stream_jobs.json").read_text(encoding="utf-8"))
        held = ROOT / "data" / "heldout" / "heldout_jobs.json"
        if env("GIGSIM_INCLUDE_HELDOUT", "0") == "1" and held.exists():
            jobs += json.loads(held.read_text(encoding="utf-8"))
            for c in json.loads((ROOT / "data" / "heldout" / "heldout_clients.json").read_text(encoding="utf-8")):
                self.clients[c["client_id"]] = c
        self.jobs = {j["job_id"]: j for j in jobs + self.stream}
        for j in self.jobs.values():
            j["featured"] = int(hashlib.md5(j["job_id"].encode()).hexdigest(), 16) % 5 == 0
        self.historical = json.loads((SEED / "historical_jobs.json").read_text(encoding="utf-8"))
        self.stats = json.loads((SEED / "market_stats.json").read_text(encoding="utf-8"))

    @property
    def policy(self) -> dict:
        return self.policy_all[env("GIGSIM_POLICY_VERSION", "v1")]

    def connects_cost(self, job: dict) -> int:
        c = self.policy["connects_cost"]
        if job["budget_type"] == "hourly":
            cost = c["hourly"]
        else:
            b = job.get("budget") or 0
            cost = c["fixed_under_500"] if b < 500 else (c["fixed_500_to_1000"] if b < 1000 else c["fixed_over_1000"])
        if job.get("featured"):
            cost += c.get("featured_surcharge", 0)
        return cost


WORLD: World | None = None


class Store:
    """Mutable state in SQLite so the simulator survives restarts."""

    def __init__(self, path: str) -> None:
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        create table if not exists kv (k text primary key, v text);
        create table if not exists accounts (account text primary key, connects integer, week integer);
        create table if not exists idem (key text primary key, account text, response text);
        create table if not exists proposals (id text primary key, account text, job_id text, body text,
            status text, created real, submitted real, outcome text);
        create table if not exists threads (id text primary key, account text, job_id text, client_id text,
            proposal_id text, created real);
        create table if not exists messages (id integer primary key autoincrement, thread_id text, sender text,
            body text, intent text, created real);
        create table if not exists events (seq integer primary key autoincrement, account text, type text,
            proposal_id text, job_id text, thread_id text, payload text, due real, released integer default 0);
        """)
        self.db.commit()

    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            cur = self.db.execute(sql, args)
            rows = cur.fetchall()
            self.db.commit()
            return rows

    def sim_minutes(self) -> float:
        rows = self.q("select v from kv where k='clock_offset'")
        offset = float(rows[0]["v"]) if rows else 0.0
        start = self.q("select v from kv where k='start'")
        if not start:
            self.q("insert into kv values('start', ?)", (str(time.time()),))
            st = time.time()
        else:
            st = float(start[0]["v"])
        return (time.time() - st) * float(env("GIGSIM_SPEED", "2")) + offset

    def advance(self, minutes: float) -> None:
        rows = self.q("select v from kv where k='clock_offset'")
        offset = float(rows[0]["v"]) if rows else 0.0
        self.q("insert or replace into kv values('clock_offset', ?)", (str(offset + minutes),))


STORE: Store | None = None
RATE: dict[str, deque] = defaultdict(deque)
ERR_RNG = random.Random(13)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global WORLD, STORE
    WORLD = World()
    db_path = env("GIGSIM_DB", str(ROOT / "data" / "processed" / "gigsim_state.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    STORE = Store(db_path)
    yield


app = FastAPI(title="GigSim", version="1.0.0", lifespan=lifespan,
              description="Marketplace simulator for GigBid (synthetic data; stand-in for the course simulator).")


# --------------------------------------------------------------------------- auth, rate limit, chaos
def account_of(authorization: str = Header(default="")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    prefix = env("GIGSIM_TOKEN_PREFIX", "gs-")
    if not token.startswith(prefix) or len(token) < len(prefix) + 3:
        raise HTTPException(401, "invalid or missing bearer token")
    return token[len(prefix):]


@app.middleware("http")
async def limits(request: Request, call_next):
    if request.url.path.startswith("/v1/") and not request.url.path.startswith("/v1/admin"):
        tok = request.headers.get("authorization", "anon")
        now = time.time()
        q = RATE[tok]
        while q and now - q[0] > 60:
            q.popleft()
        limit = int(env("GIGSIM_RATE_LIMIT_PER_MIN", "60"))
        if len(q) >= limit:
            return JSONResponse({"error": "rate_limited", "detail": f"max {limit} requests/minute"}, status_code=429,
                                headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
        q.append(now)
        if ERR_RNG.random() < float(env("GIGSIM_ERROR_RATE", "0.03")):
            return JSONResponse({"error": "upstream_unavailable", "detail": "simulated 503"}, status_code=503)
    return await call_next(request)


def admin(x_admin_token: str = Header(default="")) -> None:
    if x_admin_token != env("GIGSIM_ADMIN_TOKEN", "gigsim-admin"):
        raise HTTPException(403, "admin token required")


# --------------------------------------------------------------------------- helpers
def _released_stream_ids() -> set[str]:
    minutes = STORE.sim_minutes()
    n = int(minutes / 10)  # one new stream job every 10 simulated minutes
    return {j["job_id"] for j in WORLD.stream if j["release_seq"] < n}


def public_job(j: dict) -> dict:
    out = {k: v for k, v in j.items() if not k.startswith("_") and k not in ("release_seq",)}
    out["connects_cost"] = WORLD.connects_cost(j)
    return out


def _account(acct: str) -> sqlite3.Row:
    week = int(STORE.sim_minutes() // (7 * 24 * 60))
    rows = STORE.q("select * from accounts where account=?", (acct,))
    allowance = WORLD.policy["weekly_connects"]
    if not rows:
        STORE.q("insert into accounts values(?,?,?)", (acct, allowance, week))
    elif rows[0]["week"] != week:
        STORE.q("update accounts set connects=?, week=? where account=?", (allowance, week, acct))
    return STORE.q("select * from accounts where account=?", (acct,))[0]


def _idem_get(key: str | None, acct: str) -> dict | None:
    if not key:
        return None
    rows = STORE.q("select response from idem where key=? and account=?", (key, acct))
    return json.loads(rows[0]["response"]) if rows else None


def _idem_put(key: str | None, acct: str, resp: dict) -> None:
    if key:
        STORE.q("insert or ignore into idem values(?,?,?)", (key, acct, json.dumps(resp)))


def _release_due_events() -> None:
    now = STORE.sim_minutes()
    for ev in STORE.q("select * from events where released=0 and due<=?", (now,)):
        STORE.q("update events set released=1 where seq=?", (ev["seq"],))
        payload = json.loads(ev["payload"] or "{}")
        if ev["type"] == "replied" and ev["thread_id"]:
            STORE.q("insert into messages(thread_id,sender,body,intent,created) values(?,?,?,?,?)",
                    (ev["thread_id"], "client", payload.get("message", ""), payload.get("intent"), now))
        if ev["type"] in ("viewed", "replied", "interview", "hired", "lost"):
            status = {"viewed": "viewed", "replied": "replied", "interview": "interview", "hired": "hired",
                      "lost": "lost"}[ev["type"]]
            STORE.q("update proposals set status=? where id=?", (status, ev["proposal_id"]))


def policy_check(text: str) -> list[str]:
    checks = WORLD.policy["submission_checks"]
    problems = []
    t = text.lower()
    if "off_platform_contact" in checks and re.search(r"whatsapp|telegram|\+\d[\d\s()-]{7,}|[\w.]+@[\w-]+\.[a-z]{2,}", t):
        problems.append("off_platform_contact")
    if "ai_disclosure" in checks and "drafted with ai assistance and reviewed by me." not in t:
        problems.append("missing_ai_disclosure")
    if "no_external_urls" in checks and re.search(r"https?://", t):
        problems.append("external_url")
    return problems


# --------------------------------------------------------------------------- schemas
class ProposalIn(BaseModel):
    job_id: str
    cover_letter: str = Field(min_length=20, max_length=5000)
    screening_answers: list[str] = Field(default_factory=list, max_length=10)
    bid_amount: float = Field(gt=0, le=100000)
    bid_type: str = Field(pattern="^(fixed|hourly)$")


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


# --------------------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "gigsim", "policy_version": WORLD.policy["version"]}


@app.get("/v1/policy")
def get_policy(acct: str = Depends(account_of)) -> dict:
    return WORLD.policy


@app.get("/v1/jobs")
def search_jobs(q: str = "", category: str = "", pool: str = "", limit: int = 20, offset: int = 0,
                acct: str = Depends(account_of)) -> dict:
    released = _released_stream_ids()
    terms = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1]
    out = []
    for j in WORLD.jobs.values():
        if j["pool"] == "stream" and j["job_id"] not in released:
            continue
        if pool and j["pool"] != pool:
            continue
        if category and j["category"] != category:
            continue
        hay = (j["title"] + " " + j["description"]).lower()
        if terms and not all(t in hay for t in terms):
            continue
        out.append(j)
    out.sort(key=lambda j: (j["pool"] != "stream", -j.get("release_seq", 0), j["job_id"]))
    limit = max(1, min(limit, 100))
    return {"total": len(out), "jobs": [public_job(j) for j in out[offset:offset + limit]]}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, acct: str = Depends(account_of)) -> dict:
    j = WORLD.jobs.get(job_id)
    if not j or (j["pool"] == "stream" and job_id not in _released_stream_ids()):
        raise HTTPException(404, "job not found")
    return public_job(j)


@app.get("/v1/clients/{client_id}")
def get_client(client_id: str, acct: str = Depends(account_of)) -> dict:
    c = WORLD.clients.get(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    past = [h for h in WORLD.historical if h["client_id"] == client_id][:10]
    return {"client_id": c["client_id"], "name": c["name"], "country": c["country"], "industry": c["industry"],
            "history": c["history"],
            "recent_jobs": [{"title": h["title"], "category": h["category"], "final_paid": h["final_paid"]} for h in past]}


@app.get("/v1/market/stats")
def market(category: str, acct: str = Depends(account_of)) -> dict:
    if category not in WORLD.stats:
        raise HTTPException(404, "unknown category")
    return {"category": category, **WORLD.stats[category]}


@app.get("/v1/connects")
def connects(acct: str = Depends(account_of)) -> dict:
    a = _account(acct)
    return {"balance": a["connects"], "weekly_allowance": WORLD.policy["weekly_connects"]}


@app.post("/v1/proposals", status_code=201)
def create_draft(body: ProposalIn, acct: str = Depends(account_of),
                 idempotency_key: str | None = Header(default=None)) -> dict:
    if (prev := _idem_get(idempotency_key, acct)) is not None:
        return prev
    job = WORLD.jobs.get(body.job_id)
    if not job:
        raise HTTPException(404, "job not found")
    pid = "pr-" + hashlib.sha1(f"{acct}|{body.job_id}|{idempotency_key or time.time()}".encode()).hexdigest()[:10]
    STORE.q("insert into proposals values(?,?,?,?,?,?,?,?)",
            (pid, acct, body.job_id, body.model_dump_json(), "draft", time.time(), None, None))
    resp = {"proposal_id": pid, "status": "draft", "connects_cost": WORLD.connects_cost(job)}
    _idem_put(idempotency_key, acct, resp)
    return resp


@app.post("/v1/proposals/{proposal_id}/submit")
def submit(proposal_id: str, acct: str = Depends(account_of), idempotency_key: str | None = Header(default=None)) -> dict:
    if (prev := _idem_get(idempotency_key, acct)) is not None:
        return {**prev, "idempotent_replay": True}
    rows = STORE.q("select * from proposals where id=? and account=?", (proposal_id, acct))
    if not rows:
        raise HTTPException(404, "proposal not found")
    p = rows[0]
    if p["status"] != "draft":  # already submitted: never spend Connects twice
        return {"proposal_id": proposal_id, "status": p["status"], "idempotent_replay": True}
    body = json.loads(p["body"])
    job = WORLD.jobs[p["job_id"]]
    problems = policy_check(body["cover_letter"] + " " + " ".join(body["screening_answers"]))
    if problems:
        raise HTTPException(422, {"error": "policy_violation", "problems": problems,
                                  "policy_version": WORLD.policy["version"]})
    cost = WORLD.connects_cost(job)
    a = _account(acct)
    if a["connects"] < cost:
        raise HTTPException(402, {"error": "insufficient_connects", "balance": a["connects"], "cost": cost})
    STORE.q("update accounts set connects=connects-? where account=?", (cost, acct))
    client = WORLD.clients.get(job["client_id"], {})
    outcome = client_model.decide(job, job.get("_hidden", {}), acct, body["cover_letter"], body["bid_amount"],
                                  body["bid_type"], bool(client.get("scam")))
    now = STORE.sim_minutes()
    STORE.q("update proposals set status='submitted', submitted=?, outcome=? where id=?",
            (time.time(), json.dumps(outcome), proposal_id))
    rng = random.Random(proposal_id)
    STORE.q("insert into events(account,type,proposal_id,job_id,payload,due) values(?,?,?,?,?,?)",
            (acct, "viewed", proposal_id, job["job_id"], "{}", now + rng.uniform(5, 60)))
    if outcome["replied"]:
        tid = "th-" + proposal_id[3:]
        STORE.q("insert or ignore into threads values(?,?,?,?,?,?)",
                (tid, acct, job["job_id"], job["client_id"], proposal_id, time.time()))
        intent, msg = client_model.reply_message(job, job.get("_hidden", {}), outcome, body["bid_amount"], rng)
        STORE.q("insert into events(account,type,proposal_id,job_id,thread_id,payload,due) values(?,?,?,?,?,?,?)",
                (acct, "replied", proposal_id, job["job_id"], tid, json.dumps({"message": msg, "intent": intent}),
                 now + rng.uniform(60, 240)))
    else:
        STORE.q("insert into events(account,type,proposal_id,job_id,payload,due) values(?,?,?,?,?,?)",
                (acct, "lost", proposal_id, job["job_id"], "{}", now + rng.uniform(600, 1440)))
    resp = {"proposal_id": proposal_id, "status": "submitted", "connects_spent": cost,
            "balance": a["connects"] - cost}
    _idem_put(idempotency_key, acct, resp)
    return resp


@app.get("/v1/proposals")
def list_proposals(acct: str = Depends(account_of)) -> dict:
    _release_due_events()
    rows = STORE.q("select id, job_id, status, created, submitted from proposals where account=? order by created desc",
                   (acct,))
    return {"proposals": [dict(r) for r in rows]}


@app.get("/v1/proposals/{proposal_id}")
def get_proposal(proposal_id: str, acct: str = Depends(account_of)) -> dict:
    _release_due_events()
    rows = STORE.q("select id, job_id, status, body, created, submitted from proposals where id=? and account=?",
                   (proposal_id, acct))
    if not rows:
        raise HTTPException(404, "proposal not found")
    r = dict(rows[0])
    r["body"] = json.loads(r["body"])
    return r


@app.get("/v1/threads")
def threads(acct: str = Depends(account_of)) -> dict:
    _release_due_events()
    rows = STORE.q("select t.*, (select count(*) from messages m where m.thread_id=t.id) as n from threads t "
                   "where account=? order by created desc", (acct,))
    return {"threads": [dict(r) for r in rows if r["n"] > 0]}


@app.get("/v1/threads/{thread_id}/messages")
def thread_messages(thread_id: str, acct: str = Depends(account_of)) -> dict:
    _release_due_events()
    if not STORE.q("select 1 from threads where id=? and account=?", (thread_id, acct)):
        raise HTTPException(404, "thread not found")
    rows = STORE.q("select id, sender, body, intent, created from messages where thread_id=? order by id", (thread_id,))
    return {"thread_id": thread_id, "messages": [dict(r) for r in rows]}


@app.post("/v1/threads/{thread_id}/messages", status_code=201)
def send_message(thread_id: str, body: MessageIn, acct: str = Depends(account_of),
                 idempotency_key: str | None = Header(default=None)) -> dict:
    if (prev := _idem_get(idempotency_key, acct)) is not None:
        return {**prev, "idempotent_replay": True}
    t = STORE.q("select * from threads where id=? and account=?", (thread_id, acct))
    if not t:
        raise HTTPException(404, "thread not found")
    problems = [p for p in policy_check(body.body) if p == "off_platform_contact"]
    if problems:
        raise HTTPException(422, {"error": "policy_violation", "problems": problems})
    now = STORE.sim_minutes()
    STORE.q("insert into messages(thread_id,sender,body,intent,created) values(?,?,?,?,?)",
            (thread_id, "freelancer", body.body, None, now))
    th = t[0]
    prop = STORE.q("select outcome from proposals where id=?", (th["proposal_id"],))
    outcome = json.loads(prop[0]["outcome"] or "{}") if prop else {}
    rng = random.Random(f"{thread_id}-{len(body.body)}")
    if outcome.get("interview") and re.search(r"\b(mon|tue|wed|thu|fri)[a-z]*\b.*\d", body.body.lower()):
        STORE.q("insert into events(account,type,proposal_id,job_id,thread_id,payload,due) values(?,?,?,?,?,?,?)",
                (acct, "interview", th["proposal_id"], th["job_id"], thread_id, "{}", now + rng.uniform(30, 120)))
        STORE.q("insert into events(account,type,proposal_id,job_id,thread_id,payload,due) values(?,?,?,?,?,?,?)",
                (acct, "hired" if outcome.get("hired") else "lost", th["proposal_id"], th["job_id"], thread_id, "{}",
                 now + rng.uniform(1440, 2880)))
    resp = {"thread_id": thread_id, "status": "sent"}
    _idem_put(idempotency_key, acct, resp)
    return resp


@app.get("/v1/events")
def events(since: int = 0, acct: str = Depends(account_of)) -> dict:
    _release_due_events()
    rows = STORE.q("select seq, type, proposal_id, job_id, thread_id from events where account=? and released=1 "
                   "and seq>? order by seq", (acct, since))
    return {"events": [dict(r) for r in rows]}


# --------------------------------------------------------------------------- admin (simulation control)
@app.post("/v1/admin/advance", dependencies=[Depends(admin)])
def advance(minutes: float = 60) -> dict:
    STORE.advance(minutes)
    _release_due_events()
    return {"sim_minutes": round(STORE.sim_minutes(), 1), "released_stream_jobs": len(_released_stream_ids())}


@app.get("/v1/admin/outcome/{proposal_id}", dependencies=[Depends(admin)])
def admin_outcome(proposal_id: str) -> dict:
    rows = STORE.q("select outcome, status from proposals where id=?", (proposal_id,))
    if not rows:
        raise HTTPException(404, "proposal not found")
    return {"status": rows[0]["status"], "outcome": json.loads(rows[0]["outcome"] or "null")}


@app.post("/v1/admin/evaluate", dependencies=[Depends(admin)])
def admin_evaluate(body: dict[str, Any]) -> dict:
    """Score a proposal text against a job's simulated client WITHOUT submitting (used by offline evals)."""
    job = WORLD.jobs.get(body["job_id"])
    if not job:
        raise HTTPException(404, "job not found")
    client = WORLD.clients.get(job["client_id"], {})
    return client_model.decide(job, job.get("_hidden", {}), body.get("account", "eval"), body["text"],
                               body.get("bid_amount"), body.get("bid_type", job["budget_type"]), bool(client.get("scam")))
