"""Ingest a GitHub repository's README and source files into a portfolio through the official GitHub MCP server
(third-party; read-only). Writes repos/<name>/ into the user's tenant folder; the Portfolio server re-indexes
incrementally on the next query.

    python -m rag.ingest.github_ingest owner/repo --tenant u-123 [--project-id proj-x]
Requires GITHUB_PERSONAL_ACCESS_TOKEN (fine-grained, public repo contents read-only).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path

from common.settings import ROOT, get_settings

CODE_EXT = (".py", ".ts", ".tsx", ".js", ".sql", ".ipynb", ".R", ".yml", ".yaml")


async def _call(session, tool: str, args: dict):
    res = await session.call_tool(tool, args)
    if res.isError:
        raise RuntimeError(" ".join(getattr(c, "text", "") for c in res.content)[:300])
    for c in res.content:
        if getattr(c, "type", "") == "resource" and hasattr(c.resource, "text"):
            return c.resource.text
        if getattr(c, "text", None):
            return c.text
    return ""


async def ingest(repo: str, tenant: str, project_id: str | None = None, max_files: int = 12) -> Path:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    s = get_settings()
    if not s.github_personal_access_token:
        raise SystemExit("set GITHUB_PERSONAL_ACCESS_TOKEN (read-only fine-grained PAT)")
    owner, name = repo.split("/", 1)
    client = MultiServerMCPClient({"github": {"transport": "streamable_http", "url": s.github_mcp_url,
                                              "headers": {"Authorization": f"Bearer {s.github_personal_access_token}"}}})
    out = ROOT / "data" / "tenants" / tenant / "repos" / name
    out.mkdir(parents=True, exist_ok=True)
    async with client.session("github") as session:
        readme = await _call(session, "get_file_contents", {"owner": owner, "repo": name, "path": "README.md"})
        (out / "README.md").write_text(readme, encoding="utf-8")
        listing = await _call(session, "get_file_contents", {"owner": owner, "repo": name, "path": "/"})
        try:
            entries = json.loads(listing)
        except json.JSONDecodeError:
            entries = []
        files = [e["path"] for e in entries if isinstance(e, dict) and e.get("type") == "file" and e["path"].endswith(CODE_EXT)]
        for path in files[:max_files]:
            txt = await _call(session, "get_file_contents", {"owner": owner, "repo": name, "path": path})
            try:
                txt = base64.b64decode(txt).decode() if txt and not txt.strip().startswith(("{", "#", "import", "from")) else txt
            except Exception:  # noqa: BLE001
                pass
            (out / Path(path).name).write_text(txt, encoding="utf-8")
    (out / ".project_id").write_text(project_id or name, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--project-id")
    a = ap.parse_args()
    print(asyncio.run(ingest(a.repo, a.tenant, a.project_id)))


if __name__ == "__main__":
    main()
