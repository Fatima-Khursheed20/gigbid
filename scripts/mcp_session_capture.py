"""Capture a real MCP client session against the running Portfolio server (streamable HTTP) as an HTML page.

    python -m mcp_servers.portfolio.server --http --port 8101 &      # PORTFOLIO_DIR=data/personas/ai_ml
    python -m scripts.mcp_session_capture http://127.0.0.1:8101/mcp docs/images/mcp_session.html

This is evidence from the official MCP Python SDK client, NOT a screenshot of the MCP Inspector UI.
"""

from __future__ import annotations

import asyncio
import html
import json
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _j(x) -> str:
    return html.escape(json.dumps(x, indent=1, default=str)[:2500])


async def main(url: str, out: str) -> None:
    rows = []
    async with streamablehttp_client(url) as (r, w, _), ClientSession(r, w) as s:
        init = await s.initialize()
        rows.append(("initialize", {"server": init.serverInfo.model_dump(), "protocol": init.protocolVersion}))
        tools = (await s.list_tools()).tools
        rows.append(("tools/list", [{"name": t.name, "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
                                     for t in tools]))
        rows.append(("resources/list", [str(x.uri) for x in (await s.list_resources()).resources]))
        rows.append(("prompts/list", [p.name for p in (await s.list_prompts()).prompts]))
        name = next(t.name for t in tools if "search" in t.name)
        args = {"requirement": "LangGraph agent with a human approval step", "k": 3}
        t0 = time.time()
        res = await s.call_tool(name, args)
        rows.append((f"tools/call {name} ({time.time() - t0:.1f}s)", {"arguments": args,
                     "result": [c.model_dump() for c in res.content][:1], "isError": res.isError}))
    body = "".join(f"<h2>{html.escape(k)}</h2><pre>{_j(v)}</pre>" for k, v in rows)
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Portfolio MCP session</title><style>
body{{font:14px system-ui,sans-serif;margin:24px;background:#fff;color:#111;max-width:1100px}}
pre{{background:#f4f4f4;padding:10px;white-space:pre-wrap;font-size:12px}}h2{{font-size:15px;margin:18px 0 4px}}
.n{{color:#a33;font-weight:600}}</style></head><body><h1>gigbid-portfolio MCP server: live client session</h1>
<p class="n">Captured {time.strftime('%Y-%m-%d %H:%M')} with the official MCP Python SDK client over streamable HTTP ({html.escape(url)}).
This is not the MCP Inspector UI.</p>{body}</body></html>"""
    Path(out).write_text(page, encoding="utf-8")
    print("wrote", out, [k for k, _ in rows])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
