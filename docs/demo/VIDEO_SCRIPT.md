# 3-minute demo video — shot list and narration (record yourself; ~430 words)

Record the screen on https://gigbid-p090.onrender.com (or `python -m scripts.run_stack` locally) signed in as
the reviewer. The frames in `docs/demo/frames/` show every shot.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:20 | Inbox | "GigBid is a multi-agent freelancer copilot. Scheduled scouting fills this inbox; each job is ranked by fit with a risk badge, a recommended action, a price and its Connects cost. Nothing leaves without my approval." |
| 0:20–0:45 | Scam job detail | "This post asks for a full working version for free. The Risk Assessor's rules flag unpaid work, so GigBid skips it and drafts nothing. Scam recall was 1.0 on dev and held-out jobs." |
| 0:45–1:10 | Injection job detail | "This post hides an instruction to AI tools: claim ten years with every technology. It's detected, neutralised and shown here. Attack success fell from 50% with a naive writer to 0% with the defences." |
| 1:10–1:50 | Job detail → evidence matrix → Proposal studio, hover a claim | "For a good job, three agents ran in parallel. Each requirement maps to portfolio evidence, or to 'none', which means we never claim it. In the studio every underlined claim shows its evidence on hover. The verifier removed or rewrote unsupported claims, the Critic sent it back at most twice, and Compliance checked the policy pack." |
| 1:50–2:15 | Approve; dry-run preview; Pipeline | "The preview shows exactly what is sent and that it costs 12 Connects. I approve: it's an interrupt in a Postgres checkpoint, so it survives a crash. On the live app I restarted the server right after approving and it still submitted exactly once." |
| 2:15–2:40 | Messages | "When a client replies, the conversation graph classifies intent. Here it's an interview request, so it proposes real free calendar slots. Again, I approve before it's sent." |
| 2:40–3:00 | Run viewer, Analytics | "Every run is traced node by node with tokens, cost and latency, with one trace id through the API, MCP servers and audit log. The most surprising finding: retrieval was fine, but one uncalibrated grading threshold was skipping half the good jobs. Calibrating it took F1 from 0.71 to 0.91." |
