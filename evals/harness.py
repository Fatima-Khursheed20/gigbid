"""Shared evaluation harness: the REAL bid graph, real MCP servers (in-memory sessions) and an in-process GigSim.
No network hops except the LLM provider, so measured latency is agent latency, not localhost HTTP."""

from __future__ import annotations

import json
import os
import statistics
from pathlib import Path

import httpx

from common.settings import ROOT

PERSONAS = ["ai_ml", "fullstack", "data_analyst"]
RESULTS = ROOT / "evals" / "results"
PROFILE_ARGS = {
    "ai_ml": dict(hourly_rate=45, floor_rate=30, min_project=300),
    "fullstack": dict(hourly_rate=35, floor_rate=22, min_project=250),
    "data_analyst": dict(hourly_rate=30, floor_rate=18, min_project=150),
}


def setup_inprocess(db_path: str = ":memory:", include_heldout: bool = False) -> None:
    os.environ["GIGSIM_ERROR_RATE"] = os.environ.get("EVAL_GIGSIM_ERROR_RATE", "0")
    os.environ["GIGSIM_RATE_LIMIT_PER_MIN"] = "100000"
    if include_heldout:
        os.environ["GIGSIM_INCLUDE_HELDOUT"] = "1"
    os.environ["DATABASE_URL"] = ""
    import gigsim.app as gs
    from mcp_servers.marketplace import server as mk

    gs.WORLD = gs.World()
    gs.STORE = gs.Store(db_path)
    mk.AUDIT.dsn = ""
    mk.AUDIT.path = ROOT / "data" / "processed" / "eval_audit.jsonl"
    from types import SimpleNamespace

    mk.get_settings = lambda: SimpleNamespace(gigsim_base_url="http://gigsim", mcp_marketplace_token="eval")
    mk.CLIENT_FACTORY = lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=gs.app), base_url="http://gigsim",
                                                  timeout=60)
    import common.config as cc

    cc.load_config.cache_clear()
    # per-user limiter is for production; evals run many jobs as one user
    cc.load_config()["marketplace"]["max_requests_per_minute"] = 100000


def load_dev(persona: str, split: str = "dev") -> list[dict]:
    path = (ROOT / "evals" / "datasets" / f"dev_{persona}.jsonl") if split == "dev" else (
        ROOT / "data" / "heldout" / f"heldout_{persona}.jsonl")
    return [json.loads(x) for x in path.open(encoding="utf-8")]


def stratified(rows: list[dict], n: int, seed: int = 0) -> list[dict]:
    """Deterministic sample that keeps the mix of job kinds."""
    import random

    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["gold"]["kind"], []).append(r)
    rng = random.Random(seed)
    out = []
    for k in sorted(by):
        take = max(1, round(n * len(by[k]) / len(rows)))
        out += rng.sample(by[k], min(take, len(by[k])))
    rng.shuffle(out)
    return out[:n]


async def run_job(persona: str, job: dict, *, approve: bool = False, user: str = "eval", thread_suffix: str = "",
                  analysis_only: bool = False) -> dict:
    from agent import runtime
    from agent.nodes._base import UserProfile

    prof = UserProfile(user_id=f"{user}-{persona}", tenant=persona, **PROFILE_ARGS[persona])
    tid = f"bid:{prof.user_id}:{job['job_id']}{thread_suffix}"
    res = await runtime.run_graph("bid", profile=prof, thread_id=tid, inp={"job_id": job["job_id"], "analysis_only": analysis_only}, mode="inprocess",
                                  marketplace_token=f"gs-{prof.user_id}", dsn="")
    if approve and res["interrupt"]:
        res2 = await runtime.run_graph("bid", profile=prof, thread_id=tid, resume={"action": "approve"}, mode="inprocess",
                                       marketplace_token=f"gs-{prof.user_id}", dsn="")
        res["submit"] = res2["state"].get("submission")
        res["state_after"] = res2["state"]
    return res


def pct(xs: list[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, int(round(q * (len(xs) - 1)))))
    return round(xs[k], 3)


def mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 4) if xs else None


def write(name: str, obj: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    return p
