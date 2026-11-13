"""A tenant's portfolio corpus with lazily-built indexes shared by all retrieval variants."""

from __future__ import annotations

import json
from collections import defaultdict
from functools import cached_property
from pathlib import Path

from common.config import cfg

from .index.stores import BM25Index, DenseIndex
from .ingest.chunkers import Chunk, fixed_chunks, structured_chunks
from .ingest.loaders import Doc, load_dir


class Corpus:
    def __init__(self, root: Path | str, tenant: str | None = None, docs: list[Doc] | None = None) -> None:
        self.root = Path(root)
        self.tenant = tenant or self.root.name
        self.docs = docs if docs is not None else load_dir(self.root, self.tenant)
        self.context_lines: dict[str, str] = {}
        ctx = self.root.parent.parent / "processed" / "contextual" / f"{self.tenant}.json"
        if ctx.exists():
            self.context_lines = json.loads(ctx.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ chunk sets
    @cached_property
    def chunks(self) -> list[Chunk]:
        return structured_chunks(self.docs, cfg("rag", "chunk_chars", default=700))

    @cached_property
    def naive_chunks(self) -> list[Chunk]:
        return fixed_chunks(self.docs, cfg("rag", "naive_chunk_chars", default=400))

    @cached_property
    def by_id(self) -> dict[str, Chunk]:
        return {c.id: c for c in self.chunks} | {c.id: c for c in self.naive_chunks}

    # ------------------------------------------------------------------ indexes
    @cached_property
    def dense(self) -> DenseIndex:
        return DenseIndex(self.chunks)

    @cached_property
    def bm25(self) -> BM25Index:
        return BM25Index(self.chunks)

    @cached_property
    def naive_dense(self) -> DenseIndex:
        return DenseIndex(self.naive_chunks)

    def contextual_text(self, c: Chunk) -> str:
        line = self.context_lines.get(c.id)
        if not line:  # metadata template when no LLM-generated context line exists
            m = c.meta
            what = {"case_study": "case study", "readme": "repository README", "code": "source file",
                    "review": "client review", "proposal": "past proposal", "cv": "CV entry"}.get(m.get("type"), "document")
            line = (f"This {what} is about the project '{m.get('project') or 'general profile'}'"
                    f"{' for a ' + m['client_industry'] + ' client' if m.get('client_industry') else ''}"
                    f"{' (' + m['date'] + ')' if m.get('date') else ''}.")
        return f"{line}\n{c.text}"

    @cached_property
    def contextual_dense(self) -> DenseIndex:
        return DenseIndex(self.chunks, [self.contextual_text(c) for c in self.chunks])

    @cached_property
    def contextual_bm25(self) -> BM25Index:
        return BM25Index(self.chunks, [self.contextual_text(c) for c in self.chunks])

    # ------------------------------------------------------------------ outcome statistics (for V4)
    @cached_property
    def project_outcomes(self) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = defaultdict(lambda: {"won": 0, "replied": 0, "ignored": 0})
        for d in self.docs:
            if d.type == "proposal" and d.meta.get("outcome"):
                for pid in d.meta.get("cited_project_ids") or []:
                    stats[pid][d.meta["outcome"]] += 1
        return dict(stats)

    def project_ids(self) -> list[str]:
        return sorted({c.meta["project_id"] for c in self.chunks if c.meta.get("project_id")})

    def evidence(self, c: Chunk, score: float) -> dict:
        m = c.meta
        return {"evidence_id": c.id, "project_id": m.get("project_id"), "project": m.get("project"),
                "type": m.get("type"), "source": c.doc_id, "date": m.get("date"), "outcome": m.get("outcome"),
                "client_industry": m.get("client_industry"), "skills": m.get("skills", []),
                "score": round(float(score), 4), "text": c.text}
