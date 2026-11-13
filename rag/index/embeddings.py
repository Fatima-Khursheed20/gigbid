"""Open embedding model + open cross-encoder reranker on CPU (fastembed / ONNX), with a persistent vector cache."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from common.config import cfg
from common.settings import ROOT

CACHE_DIR = Path(os.environ.get("EMB_CACHE_DIR", ROOT / ".cache"))
FASTEMBED_CACHE = os.environ.get("FASTEMBED_CACHE_PATH", str(ROOT / ".cache" / "fastembed"))


class Embedder:
    def __init__(self, model: str | None = None) -> None:
        from fastembed import TextEmbedding

        self.model_name = model or cfg("models", "embeddings", default="BAAI/bge-small-en-v1.5")
        self.model = TextEmbedding(self.model_name, cache_dir=FASTEMBED_CACHE)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(CACHE_DIR / "emb_cache.sqlite"), check_same_thread=False)
        self.db.execute("create table if not exists e (k text primary key, v blob)")
        self.lock = threading.Lock()

    def _key(self, text: str, kind: str) -> str:
        return hashlib.sha1(f"{self.model_name}|{kind}|{text}".encode()).hexdigest()

    def embed(self, texts: list[str], kind: str = "doc") -> np.ndarray:
        keys = [self._key(t, kind) for t in texts]
        out: list[np.ndarray | None] = [None] * len(texts)
        with self.lock:
            for i, k in enumerate(keys):
                r = self.db.execute("select v from e where k=?", (k,)).fetchone()
                if r:
                    out[i] = np.frombuffer(r[0], dtype=np.float32)
        missing = [i for i, v in enumerate(out) if v is None]
        if missing:
            src = [texts[i] for i in missing]
            if kind == "query" and hasattr(self.model, "query_embed"):
                vecs = list(self.model.query_embed(src))
            else:
                vecs = list(self.model.embed(src, batch_size=32))
            with self.lock:
                for i, v in zip(missing, vecs, strict=True):
                    v = np.asarray(v, dtype=np.float32)
                    v = v / (np.linalg.norm(v) + 1e-9)
                    out[i] = v
                    self.db.execute("insert or replace into e values(?,?)", (keys[i], v.tobytes()))
                self.db.commit()
        return np.vstack(out) if out else np.zeros((0, 384), dtype=np.float32)


class Reranker:
    def __init__(self, model: str | None = None) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model_name = model or cfg("models", "reranker", default="Xenova/ms-marco-MiniLM-L-6-v2")
        self.model = TextCrossEncoder(self.model_name, cache_dir=FASTEMBED_CACHE)
        self._cache: dict[str, float] = {}

    def score(self, query: str, docs: list[str]) -> list[float]:
        keys = [hashlib.sha1(f"{query}|{d}".encode()).hexdigest() for d in docs]
        todo = [i for i, k in enumerate(keys) if k not in self._cache]
        if todo:
            scores = list(self.model.rerank(query, [docs[i] for i in todo], batch_size=32))
            for i, s in zip(todo, scores, strict=True):
                self._cache[keys[i]] = float(s)
        return [self._cache[k] for k in keys]


@lru_cache(maxsize=4)
def get_embedder(model: str | None = None) -> Embedder:
    return Embedder(model)


@lru_cache(maxsize=4)
def get_reranker(model: str | None = None) -> Reranker:
    return Reranker(model)
