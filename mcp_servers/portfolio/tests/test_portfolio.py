"""Portfolio MCP server through an in-memory MCP client (A7)."""

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.portfolio.server import mcp


@pytest.fixture(autouse=True)
def _tenant(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_TENANT", "ai_ml")


async def test_tools_are_read_only():
    async with create_connected_server_and_client_session(mcp) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert {"search_evidence", "get_case_study", "list_skills", "requirement_matrix"} <= set(tools)
        for t in tools.values():
            assert t.annotations.readOnlyHint is True
            assert t.outputSchema is not None


async def test_search_evidence_returns_typed_items():
    async with create_connected_server_and_client_session(mcp) as s:
        r = await s.call_tool("search_evidence", {"requirement": "background task queue with retries (Celery)", "k": 5})
        assert not r.isError
        items = r.structuredContent["items"]
        assert 1 <= len(items) <= 5
        for it in items:
            assert {"type", "source", "date", "outcome", "project_id"} <= set(it)
        # the doc-workers repo only reveals Celery in code; hybrid + rerank should surface that project
        assert "ai-15" in [i["project_id"] for i in items]


async def test_filters_and_constraints():
    async with create_connected_server_and_client_session(mcp) as s:
        r = await s.call_tool("search_evidence", {"requirement": "won proposals about RAG", "k": 5,
                                                  "filters": {"types": ["proposal"]}})
        assert all(i["type"] == "proposal" for i in r.structuredContent["items"])
        bad = await s.call_tool("search_evidence", {"requirement": "x", "k": 99})
        assert bad.isError


async def test_case_study_resource_and_prompts():
    async with create_connected_server_and_client_session(mcp) as s:
        cs = await s.call_tool("get_case_study", {"case_id": "ai-01"})
        assert "Contract Q&A" in cs.structuredContent["title"]
        res = await s.read_resource("portfolio://case/ai-01")
        assert "Clausewise" in res.contents[0].text
        prof = json.loads((await s.read_resource("portfolio://profile")).contents[0].text)
        assert prof["persona"] == "ai_ml"
        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert "answer_screening_question" in prompts
        templates = {t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates}
        assert {"portfolio://case/{case_id}", "portfolio://proposal/{proposal_id}"} <= templates


async def test_list_skills_includes_code_only_skills():
    async with create_connected_server_and_client_session(mcp) as s:
        r = await s.call_tool("list_skills", {})
        skills = {e["skill"] for e in r.structuredContent["skills"]}
        assert "Celery" in skills  # only appears in source code, never named in prose
