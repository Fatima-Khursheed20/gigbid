# Signature extension: X1 — Agency mode

**What:** a team of freelancers (here: the three personas — AI/ML engineer, full-stack developer, data analyst)
shares one GigBid. For every job, GigBid routes it to the best-fit member and drafts in that member's voice.

**How it works**
- `agent/agency.py::route(job, members)` runs each member's Portfolio MCP `requirement_matrix` (the same calibrated
  corrective retrieval the Fit Matcher uses) and scores fit per member; the highest fit wins. A routing is marked
  *confident* when the winner leads the runner-up by ≥ 0.10 fit.
- The bid graph then runs for the routed member's tenant: their portfolio, their rates and floor, and their
  `profile.voice` (e.g. *"direct, technical, numbers-first"* vs *"friendly, outcome-focused, short sentences"*),
  which the Writer receives as an explicit instruction (`agent/nodes/writer.py`).
- Nothing about approvals changes: the routed member still approves every proposal.

**How it was measured** (`python -m evals.runners.agency_routing`, results in `evals/results/agency_routing.json`)
- Gold: each dev job was generated for one persona, and on jobs that persona should bid on, it is the right member.
- Baseline: route by the marketplace category the client chose (ai_ml → AI/ML engineer, web → full-stack, data → analyst).
- Metrics: routing accuracy overall and per member, share of confident routings and accuracy when confident.

**Honest caveat:** on this synthetic set the category baseline is very strong by construction (each job's category
was drawn from its persona), so the extension's value is clearest on jobs whose category is ambiguous or wrong,
and on *which* member's evidence is strongest when two could do the job. Real marketplaces mis-categorise far more
often; this is stated as a limitation rather than claimed as a win.
