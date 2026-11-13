"""Arq worker on Redis:  arq worker.main.WorkerSettings"""

from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from apps.api import db
from common.pii import setup_logging
from common.settings import get_settings

from . import tasks


async def startup(ctx) -> None:
    setup_logging()
    await db.migrate()


async def shutdown(ctx) -> None:
    await db.close()


class WorkerSettings:
    functions = [tasks.analyse_job, tasks.resume_bid, tasks.replay_bid, tasks.draft_reply, tasks.resume_conv, tasks.scout]
    cron_jobs = [
        cron(tasks.scout_due, minute=set(range(0, 60, 10)), run_at_startup=True),
        cron(tasks.poll_events, minute=set(range(0, 60, 2))),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379/0")
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 900
    keep_result = 3600
    allow_abort_jobs = True
