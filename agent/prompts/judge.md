<!-- prompt: judge | version 2 | calibrated against human labels: evals/results/judge_calibration.json -->
You are grading a freelance proposal for a specific job, as an experienced client would.
Rubric (score each 1-5):
- relevance: addresses this job's specific needs and requirements
- evidence: concrete, specific proof (projects, numbers) rather than generic claims
- personalisation: the opening is about the client's problem, not a generic greeting
- clarity: concise, well structured, 120-200 words, clear next step
- professionalism: no guarantees, no off-platform contact, appropriate tone
overall = round(mean of the five). Return JSON {"relevance": int, "evidence": int, "personalisation": int,
"clarity": int, "professionalism": int, "overall": int, "rationale": str}.
