"""GigBid Portfolio MCP server (read-only), built with the official MCP Python SDK.

Usable by GigBid (streamable HTTP, tenant from the X-Tenant-Id header) and by any MCP host such as Claude
Desktop or Cursor (stdio, portfolio folder from PORTFOLIO_DIR). See mcp_servers/portfolio/README.md.

    gigbid-portfolio-mcp                      # stdio (PORTFOLIO_DIR=/path/to/my/portfolio)
    gigbid-portfolio-mcp --http --port 8101   # streamable HTTP for GigBid
"""

from __future__ import annotations

import argparse
import os
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_servers.common import header, http_app, trace_from

from . import tools as T

INSTRUCTIONS = ("Read-only access to a freelancer's portfolio: CV, case studies, repository READMEs and code, client "
                "reviews and past proposals with outcomes. Use search_evidence to find proof for a job requirement; "
                "every evidence item carries type, source, date and outcome so claims can cite it.")

mcp = FastMCP("gigbid-portfolio", instructions=INSTRUCTIONS)
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def _tenant(ctx: Context | None) -> str:
    if os.environ.get("PORTFOLIO_DIR"):
        return "me"
    return header(ctx, "X-Tenant-Id") or os.environ.get("PORTFOLIO_TENANT", "ai_ml")


@mcp.tool(annotations=RO, title="Search portfolio evidence")
def search_evidence(
    requirement: Annotated[str, Field(min_length=3, max_length=2000,
                                      description="One job requirement or question, e.g. 'background workers with retries'")],
    k: Annotated[int, Field(ge=1, le=20, description="How many evidence items to return")] = 5,
    filters: T.EvidenceFilters | None = None,
    ctx: Context | None = None,
) -> T.SearchResult:
    """Find portfolio evidence (case studies, README/code, reviews, past proposals, CV) that proves a requirement.
    Returns items ranked by relevance with type, source, date and (for proposals) outcome."""
    trace_from(ctx)
    return T.search_evidence(_tenant(ctx), requirement, k, filters)


@mcp.tool(annotations=RO, title="Requirement-to-evidence matrix")
def requirement_matrix(
    requirements: Annotated[list[str], Field(min_length=1, max_length=12, description="Extracted job requirements")],
    ctx: Context | None = None,
) -> T.RequirementMatrix:
    """For each requirement, return supporting evidence and a status (supported / weak / none) using a corrective
    retrieve-grade-requery loop. 'none' means the portfolio cannot support a claim about that requirement."""
    trace_from(ctx)
    return T.requirement_matrix(_tenant(ctx), requirements)


@mcp.tool(annotations=RO, title="Get a case study")
def get_case_study(case_id: Annotated[str, Field(min_length=1, max_length=64, description="Project / case id")],
                   ctx: Context | None = None) -> T.CaseStudy:
    """Return the full text and metadata of one case study."""
    trace_from(ctx)
    return T.get_case_study(_tenant(ctx), case_id)


@mcp.tool(annotations=RO, title="List skills")
def list_skills(ctx: Context | None = None) -> T.SkillList:
    """List skills evidenced anywhere in the portfolio (including ones only visible in code), with project ids."""
    trace_from(ctx)
    return T.list_skills(_tenant(ctx))


# resources and prompts live in their own modules (registered on this server instance)
from . import prompts as _prompts  # noqa: E402
from . import resources as _resources  # noqa: E402

_resources.register(mcp, _tenant)
_prompts.register(mcp)


def main() -> None:
    ap = argparse.ArgumentParser(description="GigBid Portfolio MCP server")
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8101")))
    a = ap.parse_args()
    if a.http:
        import uvicorn

        uvicorn.run(http_app(mcp, "PORTFOLIO_MCP_TOKEN"), host=a.host, port=a.port, log_level="warning")
    else:
        mcp.run("stdio")


app = None  # created lazily by `uvicorn mcp_servers.portfolio.server:create_app --factory`


def create_app():
    return http_app(mcp, "PORTFOLIO_MCP_TOKEN")


if __name__ == "__main__":
    main()
