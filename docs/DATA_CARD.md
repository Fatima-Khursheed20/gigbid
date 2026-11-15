# Data card

**Everything in this repository's data is synthetic unless a field is explicitly marked `source: "kaggle"`.**
The instructor's GigSim, persona corpora, dev set and hidden test set were not included in the starter kit I
received, so I built stand-ins and label them as such everywhere (UI footer, GigSim API description, this card).
No real client data, no live-mode data and no tokens are committed.

## What exists and where

| Artefact | Path | Size | Real or synthetic | How it was made |
|---|---|---|---|---|
| Three freelancer personas (AI/ML engineer, full-stack web developer, data analyst) | `data/personas/<persona>/` | 16 / 15 / 15 projects | Synthetic | Hand-authored project catalogs (`scripts/gen/personas.py`), rendered by `scripts/gen/render.py` |
| CVs | `data/personas/*/cv.pdf` | 3 PDFs | Synthetic | ReportLab, one bullet per project ("third description") |
| Case studies | `data/personas/*/case_studies/*.md` | 46 | Synthetic | problem / what I built / results / stack; *implied* skills described, never named |
| Repositories | `data/personas/*/repos/<repo>/` | 46 repos, ~110 files | Synthetic | README (clear or deliberately vague) + code files whose imports reveal the implied skills |
| Client reviews | `data/personas/*/reviews.jsonl` | 46 | Synthetic | one per project |
| Past proposals with outcomes | `data/personas/*/proposals.jsonl` | 150 per persona | Synthetic | generated from historical jobs; outcome (won / replied / ignored) from a scoring rule that rewards specific openings and relevant evidence and penalises generic, long text |
| Clients with histories and hidden preferences | `gigsim/seed/clients.json` | 400 (15% scam) | Synthetic | `scripts/gen/jobs.py::make_clients` |
| Historical jobs (pricing statistics) | `gigsim/seed/historical_jobs.json` | 1,500 | Synthetic (validated against 53k real Kaggle postings, see below) | `make_historical`; `scripts/gen/jobs.py` takes titles/budgets/hourly ranges from `data/processed/kaggle_jobs.json` when present |
| Market statistics | `gigsim/seed/market_stats.json` | 4 categories | Derived from the historical jobs | percentiles of hourly rate and fixed price by complexity |
| Dev evaluation set (gold labels) | `evals/datasets/dev_<persona>.jsonl` | 200 per persona | Synthetic | `make_set("dev", …)` |
| Live job stream | `gigsim/seed/stream_jobs.json` | 324 (300 + 24 reposted duplicates) | Synthetic | released one job per 10 simulated minutes |
| Self-held-out test set | `data/heldout/` (git-ignored) | 60 per persona, new clients | Synthetic | different seed, new client pool; touched once for the final report |

## Job mix and gold labels (per persona, dev set)

fit 84 · vague 20 · partial-fit 24 · out-of-domain 16 · low budget 12 · scam 26 · planted prompt injection 18.

Gold labels are **correct by construction** from the generator's hidden variables:
- `bid`: in-domain (fit / vague / injection), ≥60% of required skills demonstrated by some project, budget ≥ the
  persona's minimum project and hourly max ≥ the floor rate.
- `scam`: the post contains one of six scam patterns (off-platform contact, off-platform payment, unpaid "test" work,
  up-front fee, credential request, too-good-to-be-true pay). Scam posts often name in-domain skills on purpose.
- `injection`: one of six planted instructions aimed at AI tools (canary word, contact leak, guarantee, score
  manipulation, fake experience, off-platform payment).
- `evidence`: projects whose skills overlap the job's required skills; graded by overlap count (used for nDCG).
- `fair_price_band`: hidden effort hours × market hourly p40..p75 for the category.

## Properties built to defeat naive RAG
- the same project described three ways (case study, README, CV bullet) plus proposals that cite it;
- skills *implied* rather than named (e.g. Celery appears only as `from celery import Celery`);
- vague READMEs ("Internal tooling written for a client engagement") on 40% of repos;
- requirements phrased three ways in job posts: exact tool name, capability description, vague client-speak;
- past proposals whose outcome depends on specificity, not wording overlap.

## Validation against real data (Kaggle)
I compared GigSim's synthetic market statistics with **53,058 real Upwork postings** from February 2024 (Kaggle
`asaniczka/upwork-job-postings-dataset-2024-50k-records`; raw CSV kept out of the repo, aggregates in
`evals/results/kaggle_market_comparison.json`). Median hourly rate, synthetic vs real: AI/ML $46.5 vs
$26.5 (x1.75), web $37.0 vs $22.5
(x1.64), data $30.0 vs $22.5 (x1.33). **My synthetic market is
1.3-1.75x more expensive than the real one**, so fair-price bands, the Pricing Strategist's bids and the
"price inside fair band" metric are calibrated to an optimistic market. GigSim's seed was not regenerated from the
real data because it is frozen and every dev label depends on it; the categoriser is a title-keyword heuristic
(it over-assigns "data"), so treat the comparison as indicative.

## Licensing and attribution
- All synthetic content: authored for this coursework, released with the repository (MIT).
- Kaggle Upwork datasets (asaniczka, ODC-By where stated on Kaggle): used only for the aggregate comparison below (attribution: asaniczka on Kaggle); the raw data is not redistributed.

## Limitations (read before trusting any number)
1. Gold labels and the simulated client both come from my own generator — the evaluation measures how well
   GigBid recovers rules I wrote. Real clients are noisier and less consistent.
2. The client simulator is a transparent logistic model (`gigsim/client_model.py`), not an LLM; it rewards
   must-have skill coverage, concrete numbers, personalisation and penalises generic openings, over-budget bids and
   policy violations. Reply-rate differences are therefore differences in *those* features.
3. Job texts are templated; an LLM sees through some templates (e.g. a "vision system" title with LangGraph
   requirements), which makes posts less coherent than real ones.
4. Small samples for LLM-heavy evaluations (Groq free tier: 8,000 tokens/minute per model). Sample sizes are in
   every results file.
