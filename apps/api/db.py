"""App database (Postgres). Plain SQL, async psycopg pool. Every user-data query is scoped by user_id (tenant)."""

from __future__ import annotations

import json
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from common.settings import get_settings

SCHEMA = """
create table if not exists users (
  id text primary key, email text unique not null, name text not null, password_hash text not null,
  is_reviewer boolean not null default false, created_at timestamptz not null default now());
create table if not exists profiles (
  user_id text primary key references users(id) on delete cascade, tenant text not null, persona text,
  hourly_rate real not null default 35, floor_rate real not null default 20, min_project real not null default 200,
  weekly_connects_budget int not null default 80, autonomy text not null default 'suggest',
  categories jsonb not null default '[]', marketplace_mode text not null default 'gigsim',
  onboarded boolean not null default false);
create table if not exists oauth_tokens (
  user_id text not null references users(id) on delete cascade, provider text not null, ciphertext text not null,
  updated_at timestamptz not null default now(), primary key (user_id, provider));
create table if not exists saved_searches (
  id bigserial primary key, user_id text not null references users(id) on delete cascade, name text not null,
  query text not null default '', category text not null default '', pool text not null default '',
  interval_minutes int not null default 30, enabled boolean not null default true, last_run_at timestamptz);
create table if not exists seen_jobs (
  user_id text not null, fingerprint text not null, job_id text not null, first_seen timestamptz default now(),
  primary key (user_id, fingerprint));
create table if not exists inbox (
  user_id text not null, job_id text not null, thread_id text not null, title text not null, category text,
  fit real, risk real, scam boolean, injection boolean, action text, price real, bid_type text, connects int,
  status text not null, summary jsonb, updated_at timestamptz not null default now(), primary key (user_id, job_id));
create table if not exists runs (
  id text primary key, user_id text not null, kind text not null, thread_id text not null, job_id text,
  status text not null, started_at timestamptz not null default now(), ended_at timestamptz, latency_s real,
  tokens int default 0, usd real default 0, by_node jsonb, trace_id text, error text);
create index if not exists runs_user on runs(user_id, started_at desc);
create table if not exists run_events (
  id bigserial primary key, run_id text not null, ts double precision not null, kind text not null, node text,
  data jsonb);
create index if not exists run_events_run on run_events(run_id, id);
create table if not exists pipeline (
  user_id text not null, proposal_id text not null, job_id text not null, thread_id text, stage text not null,
  category text, title text, amount real, connects int, cited_projects jsonb default '[]',
  updated_at timestamptz not null default now(), primary key (user_id, proposal_id));
create table if not exists rejections (
  id bigserial primary key, user_id text not null, job_id text not null, reason text, ts timestamptz default now());
create table if not exists portfolio_files (
  user_id text not null, tenant text not null, path text not null, content bytea not null,
  uploaded_at timestamptz default now(), primary key (tenant, path));
create table if not exists event_cursor (user_id text primary key, last_seq int not null default 0);
create table if not exists conv_threads (
  user_id text not null, thread_id text not null, job_id text, status text, intent text, last_message text,
  updated_at timestamptz default now(), primary key (user_id, thread_id));
"""

_pool: AsyncConnectionPool | None = None


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        dsn = get_settings().database_url
        _pool = AsyncConnectionPool(dsn, min_size=1, max_size=8, kwargs={"autocommit": True, "row_factory": dict_row},
                                    open=False)
        await _pool.open()
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def migrate() -> None:
    p = await pool()
    async with p.connection() as c:
        await c.execute(SCHEMA)


async def fetch(sql: str, *args: Any) -> list[dict]:
    p = await pool()
    async with p.connection() as c:
        cur = await c.execute(sql, args)
        return await cur.fetchall() if cur.description else []


async def fetchone(sql: str, *args: Any) -> dict | None:
    rows = await fetch(sql, *args)
    return rows[0] if rows else None


async def execute(sql: str, *args: Any) -> None:
    p = await pool()
    async with p.connection() as c:
        await c.execute(sql, args)


def j(v: Any) -> str:
    return json.dumps(v, default=str)
