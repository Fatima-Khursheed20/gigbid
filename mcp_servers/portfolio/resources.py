"""Portfolio MCP resource templates: hosts can load full items by URI."""

from __future__ import annotations

import json

from . import tools as T


def register(mcp, tenant_of) -> None:
    @mcp.resource("portfolio://case/{case_id}", mime_type="text/markdown", description="Full case study")
    def case_resource(case_id: str) -> str:
        return T.get_case_study(tenant_of(None), case_id).text


    @mcp.resource("portfolio://proposal/{proposal_id}", mime_type="application/json", description="Past proposal + outcome")
    def proposal_resource(proposal_id: str) -> str:
        return json.dumps(T.get_proposal(tenant_of(None), proposal_id))


    @mcp.resource("portfolio://profile", mime_type="application/json", description="Freelancer profile and rates")
    def profile_resource() -> str:
        return json.dumps(T.profile(tenant_of(None)))


