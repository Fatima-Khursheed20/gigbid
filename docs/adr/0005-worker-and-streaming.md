# ADR 0005: Arq worker + Redis pub/sub + SSE

**Status:** accepted

## Context
Long agent runs must not run inside web requests; the user must see progress.

## Decision
API enqueues deterministic Arq job ids; the worker runs graphs and publishes trace events to Redis; `/api/runs/{id}/stream` replays stored events then streams live ones.

## Consequences
Re-enqueues are idempotent; the run viewer works for finished and live runs.
