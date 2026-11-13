"""Workspace MCP server (A3, A7)."""

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.workspace.server import mcp


async def test_slots_and_idempotent_hold():
    async with create_connected_server_and_client_session(mcp) as s:
        slots = (await s.call_tool("free_slots", {"days": 5, "max_slots": 3, "start_date": "2026-11-16"})).structuredContent
        assert len(slots["slots"]) == 3
        assert len({sl["start"][:10] for sl in slots["slots"]}) == 3  # spread across days
        args = {"start": slots["slots"][0]["start"], "duration_minutes": 30, "title": "Interview: test",
                "idempotency_key": "hold-key-0001"}
        h1 = (await s.call_tool("create_interview_hold", args)).structuredContent
        h2 = (await s.call_tool("create_interview_hold", args)).structuredContent
        assert h1["hold_id"] == h2["hold_id"]
        d = (await s.call_tool("create_email_draft", {"to": "client@gigsim", "subject": "Slots", "body": "Hi",
                                                      "idempotency_key": "draft-mail-001"})).structuredContent
        assert d["status"] == "draft"
