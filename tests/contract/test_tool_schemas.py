"""MCP tool-schema snapshots (A7): CI fails when a tool signature changes unintentionally.

Regenerate deliberately with:  UPDATE_SNAPSHOTS=1 pytest tests/contract
"""

import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace

SNAP = Path(__file__).parent / "snapshots"


def _norm(tool) -> dict:
    return {"name": tool.name, "description": (tool.description or "").strip(), "inputSchema": tool.inputSchema,
            "outputSchema": tool.outputSchema,
            "annotations": tool.annotations.model_dump(exclude_none=True) if tool.annotations else None}


@pytest.mark.parametrize("name,server", [("portfolio", portfolio), ("marketplace", marketplace), ("workspace", workspace)])
async def test_tool_schema_snapshot(name, server):
    async with create_connected_server_and_client_session(server) as s:
        tools = sorted((_norm(t) for t in (await s.list_tools()).tools), key=lambda t: t["name"])
    path = SNAP / f"{name}.json"
    current = json.dumps(tools, indent=1, sort_keys=True)
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        SNAP.mkdir(parents=True, exist_ok=True)
        path.write_text(current + "\n", encoding="utf-8")
        pytest.skip(f"snapshot written: {path.name}")
    assert json.loads(current) == json.loads(path.read_text(encoding="utf-8")), (
        f"{name} MCP tool schema changed. If intentional, run UPDATE_SNAPSHOTS=1 pytest tests/contract")
