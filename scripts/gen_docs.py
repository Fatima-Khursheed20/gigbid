"""Generate docs that must stay in sync with code: graph diagrams (rendered from the compiled LangGraph graphs)
and docs/TOOLS.md (from the live MCP tool schemas)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

TRUST = {
    "portfolio": "own server; read-only; tenant from authenticated header",
    "marketplace": "own server wrapping GigSim; bearer token, per-user limiter, append-only audit",
    "workspace": "own server; local mock calendar/mail; drafts and holds only, never sends",
}
AUTH = {"portfolio": "optional bearer (PORTFOLIO_MCP_TOKEN) + X-Tenant-Id",
        "marketplace": "bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header",
        "workspace": "optional bearer (WORKSPACE_MCP_TOKEN) + X-User-Id"}


def graphs() -> None:
    from agent.graphs.bid_graph import build_bid_graph
    from agent.graphs.conversation_graph import build_conversation_graph

    (DOCS / "images").mkdir(parents=True, exist_ok=True)
    for name, fn in [("bid_graph", build_bid_graph), ("conversation_graph", build_conversation_graph)]:
        mm = fn().get_graph().draw_mermaid()
        (DOCS / "images" / f"{name}.mmd").write_text(mm, encoding="utf-8")
    print("graphs rendered")


async def tools() -> None:
    from mcp.shared.memory import create_connected_server_and_client_session

    from mcp_servers.marketplace.server import mcp as mk
    from mcp_servers.portfolio.server import mcp as pf
    from mcp_servers.workspace.server import mcp as ws

    lines = ["# MCP tool inventory", "",
             "Generated from the live servers by `python -m scripts.gen_docs` (schemas are snapshot-tested in "
             "`tests/contract/`).", "",
             "| Tool | Server | Read/Write | Annotations | Auth | Allowed agents |", "|---|---|---|---|---|---|"]
    from agent.mcp_client import ALLOWLIST

    for server, srv in [("portfolio", pf), ("marketplace", mk), ("workspace", ws)]:
        async with create_connected_server_and_client_session(srv) as s:
            for t in sorted((await s.list_tools()).tools, key=lambda x: x.name):
                a = t.annotations
                rw = "read" if a and a.readOnlyHint else "write"
                ann = ", ".join(f"{k}={v}" for k, v in (a.model_dump(exclude_none=True) if a else {}).items() if k.endswith("Hint"))
                agents = ", ".join(sorted(k for k, v in ALLOWLIST.items() if t.name in v)) or "—"
                lines.append(f"| `{t.name}` | {server} | {rw} | {ann} | {AUTH[server]} | {agents} |")
    lines += ["", "## Third-party MCP servers (not written by me)", "",
              "| Server | Use | Trust rationale |", "|---|---|---|",
              "| Upwork official MCP (`https://mcp.upwork.com/mcp`) | live marketplace adapter (`mcp_servers/marketplace/adapters/upwork_live.py`) | "
              "First-party server from the platform itself, OAuth 2.1 per user, every write is a draft the user confirms on Upwork — the only sanctioned automation path. |",
              "| GitHub official MCP (`https://api.githubcopilot.com/mcp/`) | repo README/code ingestion (`rag/ingest/github_ingest.py`) | "
              "Maintained by GitHub; used read-only with a fine-grained PAT limited to public-repo contents. |",
              "", "## Server trust notes", ""] + [f"- **{k}**: {v}" for k, v in TRUST.items()]
    (DOCS / "TOOLS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("TOOLS.md written")


if __name__ == "__main__":
    graphs()
    asyncio.run(tools())
    print(json.dumps(sorted(p.name for p in (DOCS / "images").glob("*"))))
