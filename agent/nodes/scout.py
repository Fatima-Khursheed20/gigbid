"""Scout: run saved searches (scheduled by the worker), de-duplicate, queue new jobs; intake for a bid thread."""

from __future__ import annotations

import hashlib
import re

from langchain_core.runnables import RunnableConfig

from ._base import deps, node


def fingerprint(job: dict) -> str:
    """Duplicate detection: reposts get new ids and tweaked titles, but the body and client stay the same."""
    body = re.sub(r"\s+", " ", (job.get("description") or "").lower()).strip()
    return hashlib.sha1(f"{job.get('client_id')}|{body[:600]}".encode()).hexdigest()[:16]


async def scout_saved_search(port, search: dict, seen_fingerprints: set[str]) -> list[dict]:
    """Called by the worker on each saved search's schedule. Returns NEW, de-duplicated jobs only."""
    res = await port.search_jobs("scout", query=search.get("query", ""), category=search.get("category", ""),
                                 limit=search.get("limit", 8), pool=search.get("pool", ""))
    new = []
    for j in res.get("jobs", []):
        fp = fingerprint(j)
        if fp in seen_fingerprints:
            continue
        seen_fingerprints.add(fp)
        new.append({**j, "fingerprint": fp})
    return new


@node("scout", timeout_s=40)
async def intake(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    job = state.get("job") or {}
    if not job.get("description"):
        job = await d.port.get_job("scout", state["job_id"])
    return {"job": job, "job_id": job["job_id"], "status": "analysing"}
