# ADR 0004: Human approval is a LangGraph interrupt backed by Postgres

**Status:** accepted

## Context
Nothing may be sent or Connects spent without approval; approvals must survive refreshes and crashes.

## Decision
`human_approval` / `msg_approval` call `interrupt()`; the API reads pending payloads from the checkpoint; decisions resume the thread in the worker; writes carry idempotency keys derived from thread+payload.

## Consequences
Approve-twice or crash-after-submit cannot double-submit (tested). Autonomy can auto-skip, never auto-send.
