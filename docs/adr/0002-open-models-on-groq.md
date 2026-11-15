# ADR 0002: Open-weight models via Groq, routed by node

**Status:** accepted

## Context
No GPU locally; the deployed link must work on the open profile; Groq free tier gives 8k tokens/min and 1k requests/day per model.

## Decision
Profile `open`: gpt-oss-20b for cheap nodes, qwen3.8-27b for verifier/critic, gpt-oss-120b for writer/liaison/judge; each model has its own quota so spreading nodes raises throughput. Fallback model per node. `open_alt` (qwen writer) kept for comparison; `local` profile uses Ollama.

## Consequences
Latency is dominated by rate-limit waits under evaluation load; per-node routing is a config change only.
