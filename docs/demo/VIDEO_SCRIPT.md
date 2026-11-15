# 3-minute demo video: shot list, navigation and narration

The assignment asks for one job from inbox to approved proposal, one scam caught, one injected instruction ignored
and one client reply handled. Record on the live app, https://gigbid-p090.onrender.com, signed in as the reviewer.
The login is in `data/processed/reviewer_credentials.json` (git-ignored).

## Before you press record (5 minutes)

1. Open https://gigbid-p090.onrender.com/api/health and wait until it shows a JSON response (not an error page). The free server sleeps when
   idle, and the first load takes about a minute.
2. Open https://gigbid-p090.onrender.com/login, enter the email, paste the password, then click **Sign in**.
   You land on **Job inbox**. Do this *before* recording, or cut it, so the password never appears on screen.
3. Open these two images in a second window. They are real screenshots from an earlier run of this same app,
   used for the two scenes the live account cannot show right now:
   - `docs/demo/frames/03-injection-ignored.png`
   - `docs/demo/frames/09-reply-suggested.png`, then `docs/demo/frames/10-reply-sent.png`
4. **During recording, do not click "Scout now", "Analyse now" or "Re-run analysis".** A fresh analysis can
   exceed the free server's 512 MB memory and restart it for about 5 minutes. Everything below is already analysed.
5. Optional rehearsal: walk through scenes 1, 2, 4 and 7 once without recording. Approving (scene 5) can only be
   done once per job, so don't rehearse it, or rehearse it on a backup job.

Jobs on the reviewer account as of 15 Nov, 22:40 PKT:

| Use | Job title (click this text) | Direct URL path |
|---|---|---|
| Scam caught | Looking for an experienced AI & Machine Learning freelancer: vision system | `/jobs/job-dev-ai-000` |
| Good job to approve | Build a ML pipeline with Docker and PyTorch | `/jobs/job-dev-ai-004` |
| Backup if 004 fails | LLM evaluation expert needed for ecommerce prediction m… | `/jobs/job-dev-ai-006` |
| Backup 2 | Build a prediction model with Node.js and FAISS | `/jobs/job-live-0139` |

## Shot list

### Scene 1 — Inbox (0:00–0:20)
**Navigate:** top bar → **Inbox**. Then click the **Recommended** filter tab, then **All** again.
**Point at:** one row's fit score, risk badge, recommended action, price and Connects cost.
**Say:** "GigBid is a multi-agent freelancer copilot. Scheduled scouting fills this inbox; each job is ranked by fit
with a risk badge, a recommended action, a price and its Connects cost. Nothing leaves without my approval."

### Scene 2 — Scam caught (0:20–0:45)
**Navigate:** Inbox → filter tab **Skipped** → click the title **"Looking for an experienced AI & Machine Learning
freelancer: vision system"**. Scroll to **Risk report**, then expand **Original job post (untrusted)** and point at
its last line ("complete the full working version for free as a test task").
**Say:** "This post asks for a full working version for free. The Risk Assessor's rules flag unpaid work, so GigBid
skips it and drafts nothing. Scam recall was 1.0 on both my dev and held-out jobs."

### Scene 3 — Injected instruction ignored (0:45–1:10)
**Navigate:** switch to the image window and show `03-injection-ignored.png`. Point at the **Risk report** badge
`prompt_injection` and the purple box **Ignored instruction-like text**.
**Say:** "This one is a screenshot from an earlier run of the same app. The post hides an instruction to AI tools:
claim ten years of experience with every technology listed. It's detected, shown to me here, and the writer never
sees it as an instruction. Across 18 planted attacks, success fell from 50% with a naive writer to 0% with the
defences."

### Scene 4 — Good job: evidence and proposal studio (1:10–1:50)
**Navigate:** back to the app → top bar **Inbox** → filter tab **Awaiting approval** → click **"Build a ML pipeline
with Docker and PyTorch"**. On the job page, scroll through **Requirement → evidence matrix** (status `supported` or
`none`, and **Portfolio items that prove it**). Click **Open proposal studio** (top right). In the studio, hover the
mouse over two underlined claims so their evidence pops up.
**Say:** "For a good job, three agents ran in parallel. Each requirement maps to portfolio evidence, or to 'none',
which means we never claim it. In the studio every underlined claim shows its evidence on hover. The verifier removed
or rewrote unsupported claims, the Critic could send it back at most twice, and Compliance checked the policy pack."

### Scene 5 — Approve and submit (1:50–2:15)
**Navigate:** in the studio's right-hand **Your approval** panel, point at the **dry-run preview** ("Cost: N Connects ·
balance A → B"). Click **Approve & submit**. Wait for "Connects spent". Then top bar → **Pipeline**.
**Say:** "The preview shows exactly what will be sent and what it costs in Connects. I approve. The approval is an
interrupt saved in a Postgres checkpoint, so it survives a crash: on the live app I restarted the server right after
approving and it still submitted exactly once. Here it is in the pipeline."

### Scene 6 — Client reply handled (2:15–2:40)
**Navigate:** top bar → **Messages**. If a thread is listed (a simulated client replied to one of your proposals),
click it, click **Suggest a reply**, wait for **Suggested reply**, then click **Approve & send**. If the list is empty
(it is as of 22:40 PKT), switch to the image window and show `09-reply-suggested.png`, then `10-reply-sent.png`.
**Say:** "When a client replies, the conversation graph classifies the intent. Here it's an interview request, so it
proposes real free calendar slots, and again nothing is sent until I approve." (If you used the images, add: "This
reply is from an earlier run.")

### Scene 7 — Traces and analytics (2:40–3:00)
**Navigate:** top bar → **Agent runs** → click the top run id (`run-…`) to open its timeline. Then top bar →
**Analytics** and scroll to **Cost and latency vs declared budgets**.
**Say:** "Every run is traced node by node with tokens, cost and latency, with one trace id through the API, the MCP
servers and the audit log. The most surprising finding: retrieval was fine, but one uncalibrated threshold was
skipping half the good jobs. Calibrating it took bid/skip F1 from 0.71 to 0.91."

## Honesty notes for the narration
- All jobs and clients are synthetic (GigSim stand-in); say "simulated client" rather than implying real Upwork.
- If you show the screenshots in scenes 3 and 6, say they come from an earlier run, as written above.
- Don't claim the per-proposal latency budget was met; it was not (see the report).
