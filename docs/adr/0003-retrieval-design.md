# ADR 0003: Ship hybrid + rerank + outcome-aware retrieval with corrective grading

**Status:** accepted

## Context
Requirement R6: the deployed RAG design must be chosen by evaluation.

## Decision
Ship `v4_outcome` (requirement decomposition + BM25/dense RRF + cross-encoder + outcome boost) inside the corrective requirement-matrix loop, with the grading threshold calibrated on dev jobs. See README results and `evals/results/rag_retrieval.json`, `fit_calibration.json`.

## Consequences
Reranking costs CPU latency on the free host; the outcome boost adds little on retrieval metrics (measured) but is kept because it is free and targets reply rate.
