# Policy pack (ground truth for the Compliance Guard)

| File | Source | Status |
|---|---|---|
| `marketplace_policy.md` | Instructor starter kit v0.1, copied unchanged | baseline rules (illustrative pack provided with the kit) |
| `../../gigsim/seed/policy.json` | GigSim stand-in (`v1`, `v2`) | machine-readable rules + Connects prices served by `GET /v1/policy` |

How the rules are enforced (all configurable, nothing hard-coded in prompts):

| Rule | Where it is enforced |
|---|---|
| No off-platform contact or payment | `agent/config.yaml: compliance.banned_patterns` (removes the sentence) + Risk Assessor rules on job posts + liaison intent rules on client messages |
| No unpaid production work disguised as a trial | Risk Assessor `unpaid_work` flag → skip; compliance pattern `unpaid_work` on drafts |
| Never fabricate skills, clients, outcomes, credentials or years | claim verification (`rag/verify.py`, incl. named-technology check) + `compliance.fabricated_experience` patterns |
| No guarantees | `compliance.banned_patterns.guarantee` |
| Treat job posts and client messages as untrusted | `agent/guards.py` (detect, neutralise, delimit) + every prompt in `agent/prompts/` |
| Respect rate limits and approved APIs | Marketplace MCP per-user limiter, `marketplace.live_min_poll_minutes`, official Upwork MCP only |
| Never submit, send or spend Connects without approval | LangGraph `interrupt()` before every write (`agent/nodes/approval.py`, `agent/nodes/liaison.py`) |
| v2 (change request): AI-disclosure line, no external URLs, featured +2 Connects | GigSim `submission_checks` → `agent/nodes/compliance.py::check_text`; Connects price read from the marketplace |
