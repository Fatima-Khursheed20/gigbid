"""Append-only audit log of every marketplace tool call: user, tool, arguments, result, trace id (A2).

Postgres when DATABASE_URL is set (UPDATE/DELETE blocked by a trigger), otherwise a JSONL file.
Arguments and results are PII-masked before they are written.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from common.pii import mask_obj
from common.settings import ROOT, get_settings

DDL = """
create table if not exists audit_log (
  id bigserial primary key, ts timestamptz not null default now(), user_id text not null, tool text not null,
  args jsonb not null, result jsonb, ok boolean not null, dry_run boolean not null default false, trace_id text);
create or replace function audit_log_append_only() returns trigger as $$
begin raise exception 'audit_log is append-only'; end; $$ language plpgsql;
drop trigger if exists audit_log_no_update on audit_log;
create trigger audit_log_no_update before update or delete on audit_log
  for each row execute function audit_log_append_only();
"""


class AuditLog:
    def __init__(self) -> None:
        self.dsn = get_settings().database_url
        self.lock = threading.Lock()
        self._ready = False
        self.path = Path(os.environ.get("AUDIT_LOG_PATH", ROOT / "data" / "processed" / "audit.jsonl"))

    def _ensure(self) -> None:
        if self._ready or not self.dsn:
            return
        import psycopg

        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(DDL)
        self._ready = True

    def write(self, user: str, tool: str, args: dict, result: dict | None, ok: bool, dry_run: bool, trace_id: str) -> None:
        rec = {"ts": time.time(), "user_id": user, "tool": tool, "args": mask_obj(args),
               "result": mask_obj(result) if result is not None else None, "ok": ok, "dry_run": dry_run,
               "trace_id": trace_id}
        raw = json.dumps(rec["result"], default=str)
        if len(raw) > 4000:
            rec["result"] = {"truncated": raw[:4000]}
        if self.dsn:
            try:
                import psycopg

                self._ensure()
                with psycopg.connect(self.dsn, autocommit=True) as c:
                    c.execute("insert into audit_log(user_id,tool,args,result,ok,dry_run,trace_id) values (%s,%s,%s,%s,%s,%s,%s)",
                              (user, tool, json.dumps(rec["args"], default=str), json.dumps(rec["result"], default=str),
                               ok, dry_run, trace_id))
                return
            except Exception:  # noqa: BLE001 - never lose an audit record: fall through to the file
                pass
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")


AUDIT = AuditLog()
