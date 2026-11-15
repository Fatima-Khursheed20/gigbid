# My agent's retrieval was fine. One number I never measured was quietly skipping half the good jobs.

*A technical write-up from building GigBid, a multi-agent freelancer copilot (LangGraph, MCP, open models).
All data is synthetic, and every number below comes from a results file in the repository.*

## The setup

GigBid is the kind of system that sounds simple. Freelancers waste hours scanning job feeds, paying to bid on jobs
they won't win, and sending generic proposals that clients ignore. So: a scout pulls jobs; an analyst, a risk
assessor and a fit matcher look at each job in parallel; a decision node says *skip*, *watch* or *bid*; a writer
drafts a proposal in which every claim must cite real portfolio evidence; a verifier, a critic and a compliance guard
check it; and a human approves before anything is sent. Ten agents, three MCP servers, two LangGraph graphs,
Postgres checkpoints so approvals survive a crash.

Most of the course is about retrieval, and I spent most of my effort there too. The portfolio corpus was built to
defeat naive RAG: each project appears as a case study, a README and a CV bullet; many skills are never *named* in
prose (Celery appears only as `from celery import Celery`); job posts phrase requirements three ways ("Hands-on
experience with Celery", "background task queues with retries", "long jobs should run in the background and retry if
they fail").

I measured nine retrieval variants on 165 dev jobs with gold evidence. The results were satisfying in the way
textbook results are: naive dense retrieval over fixed chunks got evidence Recall@5 of **0.45**; decomposing the job
into one query per requirement got **0.63**; adding a cross-encoder reranker got **0.69**; indexing summaries,
READMEs and code separately and returning one item per project got **0.70**, with the best MRR (0.75) and
nDCG@10 (0.70). A clean, monotone-ish story. I shipped the multi-vector pipeline and moved on.

Then I ran the decision evaluation.

## The surprise

On 72 dev jobs (the LLM analyst and risk assessor plus the retrieval-based fit matcher), bid-or-skip precision was
**1.00** and recall was **0.55**. Every job GigBid recommended was a good job, and it recommended barely half of them.
Scam detection was excellent (recall 1.00), planted prompt injections were flagged on every job that had one, and
78% of prices landed inside the fair band. But every single *vague* job, the "we need someone smart to improve our
dashboard" kind of post, was skipped.

My first instinct was to blame the model, then the prompts, then the vague job templates. None of those were
it. The cause was one line in the config:

```yaml
crag_min_score: 0.0   # cross-encoder logit below which evidence is "weak"
```

The fit matcher uses a corrective retrieval loop: for each requirement, retrieve, grade the best evidence with the
cross-encoder, re-query if it's weak, and mark the requirement *none* (do not claim it) if it's still weak. The fit
score is the share of requirements with evidence. I had picked zero as the threshold because "a positive logit
means relevant" is what you learn about MS MARCO cross-encoders. I never measured it.

On short, well-phrased requirements ("Hands-on experience with Pinecone") the best evidence scores comfortably above
zero. On vague requirements it doesn't: "make the AI follow our format reliably" against a case study about
structured outputs scores around −2. That isn't irrelevant. Ranking-wise it's the right project, but it falls below
my arbitrary line. Three of five vague requirements marked *none* is a fit of 0.4 or less, and the decision node
skips.

The retrieval metrics never saw this, because Recall@5 asks "is the right project in the top five?" It is. The
*grader* then threw it away.

## The fix was cheap, and measuring it was even cheaper

A calibration sweep over the grading threshold, the bid threshold and the weight given to "weak" evidence, on 120 dev
jobs with only the cross-encoder (no LLM calls), took a few minutes:

| Setting | Precision | Recall | F1 |
|---|---|---|---|
| what I shipped first (threshold 0, bid ≥ 0.55) | 1.00 | 0.33 | **0.50** |
| calibrated (threshold −4, bid ≥ 0.40, weak = 0.5) | 0.96 | 0.90 | **0.93** |

Same retriever, same models, same prompts. The whole change is three numbers in a YAML file.

It also explained another strange result. In the first end-to-end run, where proposals go to GigSim's simulated
clients, the *baseline* naive retriever produced fifteen proposals and the "better" outcome-aware pipeline produced
two. The better pipeline wasn't worse at retrieval. It was the only one being graded, and the grader was
mis-calibrated. Naive retrieval has no grading step, so it "supports" every requirement with whatever it found. That
looks like a feature until you read the proposals.

## Why this matters more than another retrieval variant

Three lessons I'll carry into the next agent system:

**1. A pipeline's quality is set by its least-measured component.** I had nine variants and an ablation for the
retriever, and zero measurements for the threshold that turned retrieval scores into decisions. The model was doing
its job and the evaluation harness was doing its job, but nobody owned the glue. In an agent graph, the glue
(thresholds, routing conditions, loop limits) *is* the behaviour.

**2. Retrieval metrics and decision metrics measure different things.** Recall@5 rewards putting the right project
somewhere in the top five. A corrective loop needs the right project to score *above a line*. Those are different
properties of a cross-encoder, and only one of them was in my results table.

**3. "Refuse to claim when there is no evidence" has a cost.** I built the corrective loop so the writer would never
claim experience the portfolio doesn't support, and it works: it refuses on 89% of the jobs the persona should skip.
With the wrong threshold it also refused on a quarter of the jobs the persona should *bid on*. Safety mechanisms
need the same calibration as everything else, and that calibration belongs on a dev set, not in a code comment.

## The second, smaller surprise: the verifier believed in Kubernetes

Claim verification runs between the writer and the critic: split the draft into claims, label each against the
evidence, remove or rewrite what isn't supported. In an early run the writer produced *"both deployed with Docker
and Kubernetes"*. The portfolio mentions Docker and never mentions Kubernetes. The LLM verifier labelled the claim
*supported*: it saw Docker, saw a deployment, and filled in the rest.

The fix was boring and deterministic: every technology *named* in a claim must appear in the evidence it cites, or
the claim is downgraded and the name is removed ("deployed with Docker"). LLM verifiers are good at "does this
paraphrase match", and bad at noticing a single extra noun. A twenty-line string check covers the gap they leave.

## What I'd do differently

- **Calibrate every threshold on day one**, next to the retrieval eval, and fail CI when decision F1 drops. GigBid's
  eval gate now checks bid/skip F1 and unsupported claims on every pull request.
- **Report decisions next to retrieval.** My README results table now has both, and the gap between them is the
  interesting part.
- **Treat "none" as a prediction to evaluate**, not a safe default. Refusal rate on jobs you *should* bid on belongs in
  the same table as refusal rate on jobs you should skip.

## Caveats, honestly

Everything here is synthetic: three generated personas, generated jobs with labels that are correct by construction,
and a transparent rule-based client simulator. The calibration was done on the dev split and checked on a held-out
split with new clients. The LLM-heavy evaluations used small samples because they ran on a free tier (8,000 tokens
per minute per model). The direction of the finding is robust: an uncalibrated grader turns a good retriever into a
timid agent. The exact numbers will differ on real data.

*Code, evaluation runners and every results file: github.com/Fatima-Khursheed20/gigbid.*
