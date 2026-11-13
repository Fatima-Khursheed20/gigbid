"""Marketplace MCP server against an in-process GigSim (A2, A7)."""

import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

import gigsim.app as gs
from mcp_servers.marketplace import server as mk


@pytest.fixture(autouse=True)
def gigsim_inproc(monkeypatch, tmp_path):
    gs.WORLD = gs.World()
    gs.STORE = gs.Store(":memory:")
    gs.RATE.clear()
    mk._WINDOWS.clear()
    mk.AUDIT.path = tmp_path / "audit.jsonl"
    mk.AUDIT.dsn = ""
    mk.CLIENT_FACTORY = lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=gs.app), base_url="http://gigsim")
    monkeypatch.setenv("GIGSIM_TOKEN", "gs-tester")
    monkeypatch.setattr(mk, "get_settings", lambda: type("S", (), {"gigsim_base_url": "http://gigsim",
                                                                    "mcp_marketplace_token": "t"})())
    yield
    mk.CLIENT_FACTORY = None


DRAFT = {"job_id": "job-dev-ai-001", "cover_letter": "Your post about an AI assistant matches my LangGraph support agent: "
         "61% of tickets auto-drafted with human approval.", "bid_amount": 900, "bid_type": "fixed"}


async def test_annotations():
    async with create_connected_server_and_client_session(mk.mcp) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert tools["search_jobs"].annotations.readOnlyHint is True
        assert tools["submit_proposal"].annotations.destructiveHint is True
        assert tools["submit_proposal"].annotations.idempotentHint is True
        assert tools["create_proposal_draft"].annotations.destructiveHint is False
        assert "idempotency_key" in tools["send_message"].inputSchema["required"]


async def test_dry_run_creates_nothing():
    async with create_connected_server_and_client_session(mk.mcp) as s:
        r = await s.call_tool("create_proposal_draft", {**DRAFT, "idempotency_key": "draft-key-001", "dry_run": True})
        assert r.structuredContent["dry_run"] is True and r.structuredContent["would_send"]["bid_amount"] == 900
        assert r.structuredContent["connects_cost"] > 0
        props = await s.call_tool("list_proposals", {})
        assert props.structuredContent["proposals"] == []


async def test_submit_is_idempotent_and_spends_once():
    async with create_connected_server_and_client_session(mk.mcp) as s:
        bal0 = (await s.call_tool("get_connects_balance", {})).structuredContent["balance"]
        d = (await s.call_tool("create_proposal_draft", {**DRAFT, "idempotency_key": "draft-key-002"})).structuredContent
        d2 = (await s.call_tool("create_proposal_draft", {**DRAFT, "idempotency_key": "draft-key-002"})).structuredContent
        assert d["proposal_id"] == d2["proposal_id"]
        args = {"proposal_id": d["proposal_id"], "job_id": DRAFT["job_id"], "idempotency_key": "submit-key-002"}
        first = (await s.call_tool("submit_proposal", args)).structuredContent
        again = (await s.call_tool("submit_proposal", args)).structuredContent
        other_key = (await s.call_tool("submit_proposal", {**args, "idempotency_key": "submit-key-003"})).structuredContent
        assert first["status"] == "submitted" and again["idempotent_replay"] and other_key["idempotent_replay"]
        bal1 = (await s.call_tool("get_connects_balance", {})).structuredContent["balance"]
        assert bal0 - bal1 == first["connects_cost"]


async def test_input_constraints_reject_bad_args():
    async with create_connected_server_and_client_session(mk.mcp) as s:
        r = await s.call_tool("create_proposal_draft", {**DRAFT, "bid_amount": -5, "idempotency_key": "draft-key-004"})
        assert r.isError
        r = await s.call_tool("create_proposal_draft", {**DRAFT, "idempotency_key": "bad key with spaces"})
        assert r.isError


async def test_audit_log_masks_pii(tmp_path):
    async with create_connected_server_and_client_session(mk.mcp) as s:
        await s.call_tool("create_proposal_draft", {**DRAFT, "cover_letter": DRAFT["cover_letter"] + " mail me@x.com",
                                                    "idempotency_key": "draft-key-005", "dry_run": True})
    lines = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert lines and all("me@x.com" not in json.dumps(x) for x in lines)
    assert lines[-1]["tool"] == "create_proposal_draft"


def test_http_endpoint_requires_bearer(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setenv("MCP_MARKETPLACE_TOKEN", "secret-token")
    app = mk.create_app()
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.post("/mcp", json={}).status_code == 401
