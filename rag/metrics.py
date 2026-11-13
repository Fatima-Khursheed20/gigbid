"""Retrieval metrics at the evidence-item (project) level: Recall@k, MRR, nDCG@k against gold items."""

from __future__ import annotations

import math


def project_ranking(evidence: list[dict]) -> list[str]:
    seen: list[str] = []
    for e in evidence:
        pid = e.get("project_id")
        if pid and pid not in seen:
            seen.append(pid)
    return seen


def recall_at_k(ranked: list[str], gold: dict[str, int], k: int = 5) -> float:
    if not gold:
        return float("nan")
    hits = len(set(ranked[:k]) & set(gold))
    return hits / min(len(gold), k)


def mrr(ranked: list[str], gold: dict[str, int]) -> float:
    if not gold:
        return float("nan")
    for i, p in enumerate(ranked):
        if p in gold:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(ranked: list[str], gold: dict[str, int], k: int = 10) -> float:
    if not gold:
        return float("nan")
    dcg = sum((2 ** gold.get(p, 0) - 1) / math.log2(i + 2) for i, p in enumerate(ranked[:k]))
    ideal = sorted(gold.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0
