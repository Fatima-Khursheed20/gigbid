# ADR 0001: Build a GigSim stand-in and synthetic personas

**Status:** accepted

## Context
The starter kit did not contain the instructor's GigSim, persona corpora, dev set or change-request text.

## Decision
Build `gigsim/` (REST simulator with rate limits, injected 5xx, Connects, idempotent submit, a transparent seeded client model) and a generator for three personas, 1,500 historical jobs, a 600-job labelled dev set, a live stream and a held-out set. Freeze `gigsim/` with a hash manifest that CI checks.

## Consequences
Everything is reproducible and labelled synthetic. Gold labels and client behaviour come from my own rules, so results measure agreement with those rules; this is stated in the data card and report.
