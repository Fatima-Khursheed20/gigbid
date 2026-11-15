# AI usage disclosure

**Tool:** Claude Code (Anthropic, model Claude Opus 5.5), used as a pair-programming agent in the Claude desktop
app throughout the project; it drafted most of the code in every commit of this repository under my direction
(the table below lists the areas). I remain responsible for every line and for every number in the report.

## What it was used for
| Area | Files | How |
|---|---|---|
| Synthetic data generator, GigSim stand-in | `scripts/gen/*`, `gigsim/*` | generated from my spec (job mix, scam/injection templates, hidden client preferences) |
| MCP servers and tests | `mcp_servers/**` | drafted servers, schemas, idempotency/dry-run/audit; I reviewed annotations and limits |
| RAG pipeline and variants | `rag/**` | implemented V0–V8 as switches of one pipeline so ablations toggle one component |
| LangGraph graphs and nodes | `agent/**` | drafted nodes, state, interrupts, memory rules |
| Backend, worker, web app | `apps/**`, `worker/**` | drafted routers, SSE bridge, React screens |
| Evaluation runners | `evals/**` | drafted runners; all numbers come from running them (results committed under `evals/results/`) |
| Docs | `docs/**`, `README.md` | first drafts, edited for accuracy |

## Things it got wrong that were caught (and how)
1. **Claim verification let a fabricated technology through.** The first LLM-only verifier labelled
   "deployed with Docker *and Kubernetes*" as supported although Kubernetes appears nowhere in the portfolio. Found by
   reading a smoke-run draft against its evidence. Fix: a deterministic named-technology check
   (`rag/verify.py::unsupported_tech`) that downgrades the claim and removes the unsupported tool name; the
   verifier prompt now asks for verbatim claims and `apply_labels` edits the closest real sentence when the LLM
   paraphrases.
2. **Evidence grading threshold was guessed, not measured.** The corrective-retrieval threshold (cross-encoder
   logit ≥ 0) and fit thresholds were picked by intuition. The first decision eval showed bid/skip recall 0.55
   and the first V4 outcome run produced only 2 proposals out of 15. A calibration sweep on dev jobs
   (`evals/runners/calibrate_fit.py`) moved F1 from 0.50 to 0.93; thresholds are now in config with a pointer
   to the results file.
3. **Escaping bugs in generated files.** Several edits made through shell heredocs injected literal backspace
   characters (`\b` → `\x08`) into a regex and broke string literals; one silently disabled the technology-removal
   regex. Caught by a unit check that the removal actually happened; files are now edited with a proper editor.
4. **Windows event loop.** It first ran the services with uvicorn's default Proactor loop, which async psycopg does
   not support; fixed with `scripts/serve.py` (selector loop on Windows).
5. **Over-eager compliance.** Every LLM compliance flag first hard-blocked the draft; the policy only requires
   removing violating content and blocking when the draft cannot be fixed. Caught when a clean-looking draft was
   blocked during the outcome evaluation.

6. **Quota planning.** It ran several LLM-heavy evaluations in parallel on one free-tier key and exhausted the
   daily token limits of all three models (200k tokens/day each), which left the R&D C baselines incomplete and
   pushed the held-out run onto the fallback path. Caught from 429 "tokens per day" errors in the results files;
   both limitations are reported in the R&D report instead of being re-run with cherry-picked samples.
7. **Free-tier deployment.** The single-process build first ran out of memory (512 MB) and then froze the
   event loop on a 0.1-vCPU instance, because FastMCP runs synchronous tools on the event loop. Fixed by disabling
   ONNX's memory arena, smaller batches, one worker job at a time, and running retrieval in worker threads.

## What was not delegated
Choice of datasets and their honest labelling as synthetic, the decision to report negative results, the human
labels for judge calibration and the blind pairwise panel (these must be produced by people, not the AI — see
`evals/human/`).
