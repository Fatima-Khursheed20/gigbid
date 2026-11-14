# Runbook

## Start
| Where | Command |
|---|---|
| Everything in containers | `docker compose -f infra/docker-compose.yml --env-file .env up --build` → web on :8080, API on :8000 |
| + local open models | `... --profile local up`, then `docker compose exec ollama ollama pull qwen3:4b` and `MODEL_PROFILE=local` |
| Laptop without Docker for the app (Postgres/Redis in Docker) | `uv sync --extra dev && (cd apps/web && npm ci && npm run build) && uv run python -m scripts.run_stack` |
| Public deployment (Hugging Face Docker Space) | root `Dockerfile`; secrets `DATABASE_URL` (Neon), `REDIS_URL` (Upstash, `rediss://`), `GROQ_API_KEY`, `APP_SECRET_KEY`, `MCP_MARKETPLACE_TOKEN`, `REVIEWER_EMAIL`, `REVIEWER_PASSWORD` |

Health: `GET /api/health` reports db, redis, marketplace (MCP server + GigSim), portfolio, llm and `degraded`.

## Schedules and rate limits
| Job | Interval | Why |
|---|---|---|
| `scout_due` (cron, every 10 min) | runs each saved search whose own interval elapsed; **GigSim floor 30 min**, **live Upwork floor 120 min** (`marketplace.live_min_poll_minutes`) | Upwork treats aggressive polling as scraping. New good jobs are rarely worth reacting to within minutes because a human approves every proposal anyway; two hours keeps us to ~12 reads/day/search, far below anything bot-like, while still surfacing jobs the same day. |
| `poll_events` (cron, every 2 min) | GigSim only: proposal events → pipeline, outcome memory, reply drafts | In live mode Upwork notifies through its own UI; we do not poll messages faster than the scout floor. |
| Marketplace MCP limiter | 40 requests/min per user | stays under GigSim's 60/min token limit; bursts get HTTP 429 → bounded retries with `Retry-After`. |
| LLM | 2 concurrent calls per model; honours `retry-after`; falls back to another open model; stops early on a daily-token 429 | Groq free tier: 1,000 requests/day and 8,000 tokens/minute per model. |

## Degraded mode (viva question 1: "kill the marketplace MCP server")
1. `ToolBus.call` (`agent/mcp_client.py`) retries twice with backoff, then raises `MarketplaceUnavailable`.
2. The node wrapper (`agent/nodes/_base.py::node`) maps it to `status="degraded"` and `degraded={node: reason}`;
   the graph routes to END with everything already checkpointed.
3. The inbox row shows *degraded*; `/api/health` reports the marketplace down and the web app shows the amber
   **Degraded mode** banner (`apps/web/src/components/DegradedBanner.tsx`).
4. The worker's next `scout_due` / a user "Re-run analysis" re-enqueues the job; `analyse_job` treats
   `degraded` rows as retryable. Nothing is lost and nothing is sent.

## Crash and resume (viva question 2)
Approval state lives in the Postgres checkpointer (`langgraph-checkpoint-postgres`). Kill the API or the worker at
any point: on restart `GET /api/proposals/{job}` still shows the pending approval (it reads the checkpoint), and an
approval re-enqueues `resume_bid`. The `submit` node derives its idempotency keys from the thread id and the exact
payload, and GigSim's submit is idempotent per key *and* per proposal, so a submit that ran before the crash is
replayed, not repeated. Covered by `tests/integration/test_bid_graph.py::test_fit_job_interrupts_then_submits_exactly_once`.
Replay any job from any node: Agent runs → filter by job → *Checkpoint history* → *Replay from here*.

## Switching to live Upwork (viva question 7)
`agent/config.yaml: marketplace.mode: upwork` (or `MARKETPLACE_MODE=upwork`). Only `agent/marketplace_port.py::make_port`
picks a different adapter (`UpworkLivePort`); no node, prompt or graph changes. Users connect Upwork in
Settings (OAuth 2.1 + PKCE + dynamic client registration via the MCP SDK; tokens Fernet-encrypted per user).
In live mode `submit_proposal` never submits: it leaves a draft the user confirms on Upwork.
**Status: implemented but not exercised against a live account (none available).**

## Secrets
Only from environment variables. `.env` is git-ignored; CI (`scripts/ci_checks.py`) fails on committed tokens.
OAuth tokens are encrypted at rest and masked in logs and the audit log (`common/pii.py`).

## Common problems
| Symptom | Fix |
|---|---|
| `Psycopg cannot use the 'ProactorEventLoop'` on Windows | start services through `python -m scripts.serve <name>` (sets the selector loop) |
| MCP server returns 421 / host rejected in containers | set `MCP_ALLOWED_HOSTS=*` (bearer auth still applies) |
| Runs slow, many 429s | Groq free-tier TPM; lower `LLM_CONCURRENCY` or move nodes to another model in `agent/config.yaml` |
