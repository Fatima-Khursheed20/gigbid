# Submission (Google Classroom, one submission)

Paste the block below into the submission. The reviewer login goes **only in a private comment**, never here.

```
GigBid — AI-4016 Assignment II

Deployed app:        https://gigbid-p090.onrender.com   (free tier: first load after idle takes ~1 minute)
GitHub repository:   https://github.com/Fatima-Khursheed20/gigbid
R&D report (PDF):    https://github.com/Fatima-Khursheed20/gigbid/blob/main/docs/report/GigBid_RnD_Report.pdf
Demo video (3 min):  <VIDEO LINK>
Portfolio MCP server (published, installable):
                     uvx --from git+https://github.com/Fatima-Khursheed20/gigbid gigbid-portfolio-mcp
                     https://github.com/Fatima-Khursheed20/gigbid/tree/main/mcp_servers/portfolio
Technical write-up:  https://fatima-khursheed20.github.io/gigbid/
Trace links:         https://github.com/Fatima-Khursheed20/gigbid/blob/main/docs/TRACES.md
Playwright report:   https://github.com/Fatima-Khursheed20/gigbid/tree/main/docs/playwright-report
Demo GIF:            https://github.com/Fatima-Khursheed20/gigbid/blob/main/docs/images/demo.gif
Résumé bullet:       https://github.com/Fatima-Khursheed20/gigbid/blob/main/docs/RESUME.md
AI usage:            https://github.com/Fatima-Khursheed20/gigbid/blob/main/docs/AI_USAGE.md
```

Private comment: the reviewer e-mail and password from `data/processed/reviewer_credentials.json` (git-ignored).

## Known gaps (stated in the report)
- Judge calibration: the assignment requires 30 labels made by the student; `evals/human/judge_labels.csv` is
  unlabelled, so no kappa is reported. The AI did not and must not fill these labels.
- Blind pairwise human panel: needs classmates (`evals/human/pairwise.csv`); not collected.
- MCP Inspector screenshots: launching the Inspector was blocked in the AI session; a live MCP SDK client session
  is captured instead (`docs/images/mcp_session.png`). To add Inspector screenshots:
  `npx @modelcontextprotocol/inspector uv run gigbid-portfolio-mcp` (with `PORTFOLIO_DIR=data/personas/ai_ml`).
- RAG variants V6/V7 not evaluated at scale; per-proposal p95 latency budget missed.
