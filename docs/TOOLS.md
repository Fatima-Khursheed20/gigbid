# MCP tool inventory

Generated from the live servers by `python -m scripts.gen_docs` (schemas are snapshot-tested in `tests/contract/`).

| Tool | Server | Read/Write | Annotations | Auth | Allowed agents |
|---|---|---|---|---|---|
| `get_case_study` | portfolio | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (PORTFOLIO_MCP_TOKEN) + X-Tenant-Id | baseline, writer |
| `list_skills` | portfolio | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (PORTFOLIO_MCP_TOKEN) + X-Tenant-Id | fit_matcher |
| `requirement_matrix` | portfolio | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (PORTFOLIO_MCP_TOKEN) + X-Tenant-Id | baseline, fit_matcher |
| `search_evidence` | portfolio | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (PORTFOLIO_MCP_TOKEN) + X-Tenant-Id | baseline, critic, fit_matcher, liaison, writer |
| `create_proposal_draft` | marketplace | write | readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | approval_gate, baseline |
| `get_client_history` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | baseline, risk_assessor |
| `get_connects_balance` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | approval_gate, baseline, pricing |
| `get_job` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | baseline, scout |
| `get_market_stats` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | baseline, pricing |
| `get_policy` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | pricing |
| `list_events` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | pipeline |
| `list_messages` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | liaison |
| `list_proposals` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | pipeline |
| `list_threads` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | liaison, pipeline |
| `search_jobs` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | baseline, scout |
| `send_message` | marketplace | write | readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | conv_gate |
| `submit_proposal` | marketplace | write | readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True | bearer (MCP_MARKETPLACE_TOKEN) + per-user GigSim token header | approval_gate |
| `create_email_draft` | workspace | write | readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (WORKSPACE_MCP_TOKEN) + X-User-Id | conv_gate |
| `create_interview_hold` | workspace | write | readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (WORKSPACE_MCP_TOKEN) + X-User-Id | conv_gate |
| `free_slots` | workspace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (WORKSPACE_MCP_TOKEN) + X-User-Id | liaison |
| `list_holds` | workspace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | optional bearer (WORKSPACE_MCP_TOKEN) + X-User-Id | — |

## Third-party MCP servers (not written by me)

| Server | Use | Trust rationale |
|---|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`) | live marketplace adapter (`mcp_servers/marketplace/adapters/upwork_live.py`) | First-party server from the platform itself, OAuth 2.1 per user, every write is a draft the user confirms on Upwork — the only sanctioned automation path. |
| GitHub official MCP (`https://api.githubcopilot.com/mcp/`) | repo README/code ingestion (`rag/ingest/github_ingest.py`) | Maintained by GitHub; used read-only with a fine-grained PAT limited to public-repo contents. |

## Server trust notes

- **portfolio**: own server; read-only; tenant from authenticated header
- **marketplace**: own server wrapping GigSim; bearer token, per-user limiter, append-only audit
- **workspace**: own server; local mock calendar/mail; drafts and holds only, never sends
