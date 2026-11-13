"""Bid + conversation graphs end-to-end against an in-process GigSim through real (in-memory) MCP sessions.
Runs offline (LLM_OFFLINE=1) so it is deterministic in CI; the LLM paths are exercised by the evals."""

import json

import httpx
import pytest

import gigsim.app as gs
from agent import runtime
from agent.nodes._base import UserProfile
from common.settings import ROOT
from mcp_servers.marketplace import server as mk


@pytest.fixture(autouse=True)
def world(tmp_path):
    gs.WORLD = gs.World()
    gs.STORE = gs.Store(":memory:")
    gs.RATE.clear()
    mk._WINDOWS.clear()
    mk.AUDIT.path, mk.AUDIT.dsn = tmp_path / "audit.jsonl", ""
    mk.CLIENT_FACTORY = lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=gs.app), base_url="http://gigsim")
    runtime.reset_memory()
    yield
    mk.CLIENT_FACTORY = None


def dev(persona: str, kind: str, n: int = 0) -> dict:
    rows = [json.loads(x) for x in (ROOT / "evals" / "datasets" / f"dev_{persona}.jsonl").open()]
    return [r for r in rows if r["gold"]["kind"] == kind][n]


PROFILE = UserProfile(user_id="u-test", tenant="ai_ml", hourly_rate=45, floor_rate=30, min_project=300)


async def run(job_id, **kw):
    return await runtime.run_graph("bid", profile=PROFILE, thread_id=f"bid:u-test:{job_id}", mode="inprocess",
                                   marketplace_token="gs-u-test", dsn="", **kw)


async def test_scam_is_skipped_without_drafting():
    job = dev("ai_ml", "scam")
    r = await run(job["job_id"], inp={"job_id": job["job_id"]})
    st = r["state"]
    assert st["decision"]["action"] == "skip"
    assert st["risk"]["scam"] is True
    assert "draft" not in st and r["interrupt"] is None
    assert set(st["analyses_done"]) == {"analyst", "risk", "fit"}  # the three parallel branches all ran


async def test_fit_job_interrupts_then_submits_exactly_once():
    job = next(j for j in (dev("ai_ml", "fit", i) for i in range(30)) if j["gold"]["bid"])
    r = await run(job["job_id"], inp={"job_id": job["job_id"]})
    assert r["interrupt"] and r["interrupt"]["type"] == "proposal_approval", r["state"].get("decision")
    p = r["interrupt"]
    assert p["preview"]["connects_cost"] > 0 and p["evidence"] and p["risk"] and p["price"]["rationale"]
    assert "[E" not in p["preview"]["would_send"]["cover_letter"]  # citations never leave GigBid
    bal0 = gs.STORE.q("select connects from accounts where account='u-test'")[0]["connects"]
    r2 = await run(job["job_id"], resume={"action": "approve"})
    assert r2["state"]["status"] == "submitted"
    # simulate a crash right after submit: replaying the submit node must not spend Connects twice
    r3 = await run(job["job_id"], resume={"action": "approve"})
    bal1 = gs.STORE.q("select connects from accounts where account='u-test'")[0]["connects"]
    assert bal0 - bal1 == p["preview"]["connects_cost"]
    assert r3["state"]["status"] == "submitted"


async def test_edit_goes_back_through_compliance_and_reject_records_reason():
    job = next(j for j in (dev("ai_ml", "fit", i) for i in range(30)) if j["gold"]["bid"])
    await run(job["job_id"], inp={"job_id": job["job_id"]})
    edited = ("Your project is close to work I shipped for a legal-tech client, where answers had to cite sources. "
              "I would start by mapping your requirements to a small evaluation set so we can measure progress weekly. "
              "Contact me on whatsapp +1 555 222 3333 please. Then I would build the first working slice in week one, "
              "share it with you for feedback, and harden it with tests before the handover call and written runbook.")
    r = await run(job["job_id"], resume={"action": "edit", "edited_text": edited})
    assert r["interrupt"]["type"] == "proposal_approval"
    assert "whatsapp" not in r["interrupt"]["draft"]["cover_letter"].lower()  # compliance re-checked the edit
    r2 = await run(job["job_id"], resume={"action": "reject", "reason": "too generic"})
    assert r2["state"]["status"] == "rejected" and r2["state"]["approval"]["reason"] == "too generic"


async def test_degraded_mode_when_marketplace_down():
    mk.CLIENT_FACTORY = lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(503)),
                                                  base_url="http://gigsim")
    job = dev("ai_ml", "fit")
    r = await run(job["job_id"], inp={"job_id": job["job_id"]})
    assert r["state"]["status"] == "degraded"
    assert "scout" in r["state"]["degraded"]
