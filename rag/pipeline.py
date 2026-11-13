"""Composable retrieval pipeline. Each variant V0..V8 is a preset of these switches (rag/variants/*),
so ablations toggle exactly one component and one command reruns the full comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import numpy as np

from common.config import cfg

from .corpus import Corpus
from .index.embeddings import get_reranker


@dataclass(frozen=True)
class Settings:
    name: str
    chunking: str = "structured"     # fixed | structured
    query: str = "whole"             # whole | decomposed | hyde
    hybrid: bool = False             # BM25 + dense with reciprocal rank fusion
    rerank: bool = False             # cross-encoder
    outcome: bool = False            # outcome-aware boost
    multivector: bool = False        # return one item per project, aggregating summary/README/code
    contextual: bool = False         # context line prepended before indexing
    crag: bool = False               # corrective loop (handled in variants/v8_crag.py)

    def without(self, component: str) -> Settings:
        off = {"query": "whole"} if component == "query" else {component: False}
        return replace(self, name=f"{self.name}-no_{component}", **off)


@dataclass
class Query:
    job_text: str
    requirements: list[str] = field(default_factory=list)
    hyde_text: str | None = None


REQ_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")


def heuristic_requirements(job_text: str) -> list[str]:
    """Offline requirement extraction: bullet lines under 'Requirements', else sentences that state a need."""
    lines = job_text.splitlines()
    reqs: list[str] = []
    in_req = False
    for ln in lines:
        low = ln.strip().lower()
        if low.startswith("requirements"):
            in_req = True
            continue
        if low.startswith(("deliverables", "please answer")):
            in_req = False
        m = REQ_LINE.match(ln)
        if in_req and m:
            reqs.append(m.group(1).strip())
    if not reqs:
        sents = re.split(r"(?<=[.!?])\s+", " ".join(lines))
        reqs = [s.strip() for s in sents if len(s.split()) >= 4 and not s.lower().startswith(("we are", "our ", "i run"))][:6]
    return reqs or [job_text[:300]]


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for r, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + r + 1)
    return scores


def _minmax(xs: list[float]) -> list[float]:
    if not xs:
        return xs
    lo, hi = min(xs), max(xs)
    return [0.5 if hi == lo else (x - lo) / (hi - lo) for x in xs]


class Pipeline:
    def __init__(self, corpus: Corpus, s: Settings) -> None:
        self.c, self.s = corpus, s

    # --------------------------------------------------------------- candidate generation
    def _queries(self, q: Query) -> list[str]:
        if self.s.query == "decomposed":
            return q.requirements or heuristic_requirements(q.job_text)
        if self.s.query == "hyde" and q.hyde_text:
            return [q.hyde_text]
        return [q.job_text]

    def _one(self, text: str, n: int) -> list[int]:
        if self.s.chunking == "fixed":
            return [i for i, _ in self.c.naive_dense.search(text, n)]
        dense = self.c.contextual_dense if self.s.contextual else self.c.dense
        d = [i for i, _ in dense.search(text, n)]
        if not self.s.hybrid:
            return d
        bm = self.c.contextual_bm25 if self.s.contextual else self.c.bm25
        b = [i for i, _ in bm.search(text, n)]
        fused = rrf([d, b])
        return sorted(fused, key=lambda i: -fused[i])[:n]

    def candidates(self, q: Query) -> tuple[list[int], dict[int, float], list[str]]:
        n = cfg("rag", "candidates", default=30)
        queries = self._queries(q)
        rankings = [self._one(t, n) for t in queries]
        fused = rrf(rankings)
        order = sorted(fused, key=lambda i: -fused[i])[: max(n, 8 * len(queries))]
        return order, fused, queries

    # --------------------------------------------------------------- scoring
    def retrieve(self, q: Query, k: int | None = None) -> list[dict]:
        k = k or cfg("rag", "k", default=5)
        chunks = self.c.naive_chunks if self.s.chunking == "fixed" else self.c.chunks
        order, fused, queries = self.candidates(q)
        if self.s.rerank:
            rr = get_reranker()
            texts = [chunks[i].text for i in order]
            per_q = np.array([rr.score(t[:1000], texts) for t in queries])  # (queries, candidates)
            base = per_q.max(axis=0).tolist()
        else:
            base = [fused[i] for i in order]
        scores = _minmax(base)
        if self.s.outcome:
            boost = cfg("rag", "outcome_boost", default={"won": 0.25, "replied": 0.12, "ignored": -0.05})
            po = self.c.project_outcomes
            for j, i in enumerate(order):
                m = chunks[i].meta
                b = boost.get(m.get("outcome"), 0.0) if m.get("type") == "proposal" else 0.0
                st = po.get(m.get("project_id") or "", None)
                if st:
                    n = sum(st.values())
                    b += (boost["won"] * st["won"] + boost["replied"] * st["replied"] + boost["ignored"] * st["ignored"]) / n
                scores[j] += b
        ranked = sorted(zip(order, scores, strict=True), key=lambda t: -t[1])
        if self.s.multivector:
            return self._group_projects(ranked, chunks, k)
        return [self.c.evidence(chunks[i], s) for i, s in ranked[: max(k * 4, 20)]]

    def _group_projects(self, ranked: list[tuple[int, float]], chunks, k: int) -> list[dict]:
        """V5: summary/README/code chunks are indexed separately but returned as ONE project item."""
        best: dict[str, dict] = {}
        support: dict[str, list[str]] = {}
        for i, s in ranked:
            c = chunks[i]
            pid = c.meta.get("project_id")
            if not pid:
                continue
            support.setdefault(pid, []).append(c.meta.get("type"))
            if pid not in best:
                best[pid] = self.c.evidence(c, s)
            else:
                best[pid]["score"] = round(best[pid]["score"] + 0.05 * s, 4)  # mild bonus for multiple views
        for pid, ev in best.items():
            ev["views"] = sorted(set(support[pid]))
        return sorted(best.values(), key=lambda e: -e["score"])[: max(k * 4, 20)]
