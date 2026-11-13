"""Retriever factory: the deployed variant is chosen in agent/config.yaml (rag.variant) by evaluation (R6)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from common.config import cfg

from .corpus import Corpus
from .pipeline import Pipeline, Query, Settings
from .variants import (
    v0_naive,
    v1_decompose,
    v2_hybrid,
    v3_rerank,
    v4_outcome,
    v5_multivector,
    v6_contextual,
    v7_hyde,
    v8_crag,
)

VARIANTS: dict[str, Settings] = {m.SETTINGS.name: m.SETTINGS for m in
                                 (v0_naive, v1_decompose, v2_hybrid, v3_rerank, v4_outcome, v5_multivector,
                                  v6_contextual, v7_hyde, v8_crag)}


def settings_for(name: str) -> Settings:
    if name in VARIANTS:
        return VARIANTS[name]
    raise KeyError(f"unknown RAG variant {name!r}; known: {sorted(VARIANTS)}")


def make(corpus: Corpus, name: str | Settings):
    s = name if isinstance(name, Settings) else settings_for(name)
    if s.crag:
        return v8_crag.CragRetriever(corpus, s)
    return Pipeline(corpus, s)


@lru_cache(maxsize=16)
def corpus_for(root: str, tenant: str) -> Corpus:
    return Corpus(Path(root), tenant)


def default_retriever(root: str, tenant: str):
    return make(corpus_for(root, tenant), cfg("rag", "variant", default="v3_rerank"))


__all__ = ["VARIANTS", "Query", "make", "corpus_for", "default_retriever", "settings_for"]
