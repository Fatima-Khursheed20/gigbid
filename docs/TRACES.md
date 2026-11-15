# Trace links (live deployment)

Traces are GigBid's own run viewer: node-by-node latency, tokens, USD and every MCP tool call, with the trace id
that is also stamped on every MCP request and audit-log row. Open them after signing in with the reviewer account
(credentials are shared privately with the submission). LangSmith export is supported (`LANGSMITH_*` env vars) but
was not configured, because no LangSmith key was available.

| Scenario | Run | What to look at |
|---|---|---|
| Skipped scam | [run-91350f4bbd7a](https://gigbid-p090.onrender.com/runs/run-91350f4bbd7a) | `job-dev-ai-000`: Risk Assessor flags `unpaid_work`; decision **skip**; no draft, no tool writes |
| Approved proposal | [run-b8a24ca6d117](https://gigbid-p090.onrender.com/runs/run-b8a24ca6d117) | `job-dev-ai-005`: resume after approval → `submit` → marketplace `create_proposal_draft` + `submit_proposal` (idempotency keys) |
| Critic loop | [run-ad5d56d61433](https://gigbid-p090.onrender.com/runs/run-ad5d56d61433) | `job-dev-ai-006`: `critic` ran 3 times (`revise` → `writer` → `verifier` → `critic`), then capped at 2 revisions |
| Crash-and-resume | [run-f0ca64af85d0](https://gigbid-p090.onrender.com/runs/run-f0ca64af85d0) | `job-dev-ai-001`: approved, then the Render instance was restarted via the API seconds later; after restart the run shows **submitted**, the pipeline holds exactly one proposal `pr-b27fc74575`, Connects 108 → 96 (one charge). Checkpoint history: Agent runs → filter by job. The same property is tested in `tests/integration/test_bid_graph.py`. |

Honesty note: the restart was issued immediately after the approval; I can't prove from the outside that it hit the
submit node mid-flight rather than just before or after. The exactly-once guarantee itself rests on the
idempotency keys (thread id + payload hash) and GigSim's per-proposal idempotent submit, which the integration test
exercises deterministically by replaying the submit node.
