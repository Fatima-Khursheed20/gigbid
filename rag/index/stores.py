"""Vector and BM25 indexes over chunks.

`DenseIndex` is in-process (numpy) — used by the published stdio Portfolio MCP server and offline evals.
`PgVectorIndex` stores the same vectors in Postgres/pgvector (the deployed vector store); queries are always
scoped by tenant.
"""

from __future__ import annotations

import json
import re

import numpy as np
from rank_bm25 import BM25Okapi

from ..ingest.chunkers import Chunk
from .embeddings import get_embedder

TOKEN = re.compile(r"[a-z0-9][a-z0-9+#./-]*")
STOP = set("a an the and or of to in for with on at by is are be we our you your i my it this that as from will "
           "can have has need needs looking someone who what how".split())


def tokenize(text: str) -> list[str]:
    toks = [t.strip("./-") for t in TOKEN.findall(text.lower())]
    return [t for t in toks if t and t not in STOP]


class DenseIndex:
    def __init__(self, chunks: list[Chunk], texts: list[str] | None = None) -> None:
        self.chunks = chunks
        self.emb = get_embedder()
        self.vecs = self.emb.embed(texts or [c.text for c in chunks], kind="doc")

    def search(self, query: str, k: int = 10, qvec: np.ndarray | None = None) -> list[tuple[int, float]]:
        if qvec is None:
            qvec = self.emb.embed([query], kind="query")[0]
        sims = self.vecs @ qvec
        idx = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in idx]


class BM25Index:
    def __init__(self, chunks: list[Chunk], texts: list[str] | None = None) -> None:
        self.chunks = chunks
        self.bm = BM25Okapi([tokenize(t) for t in (texts or [c.text for c in chunks])])

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        scores = self.bm.get_scores(tokenize(query))
        idx = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in idx if scores[i] > 0]


class PgVectorIndex:
    """pgvector-backed index (tenant-scoped). Used by the portfolio MCP server when DATABASE_URL is set."""

    def __init__(self, dsn: str, tenant: str, space: str) -> None:
        import psycopg
        from pgvector.psycopg import register_vector

        self.tenant, self.space = tenant, space
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.conn.execute("create extension if not exists vector")
        register_vector(self.conn)
        dim = len(get_embedder().embed(["x"], kind="doc")[0])
        self.conn.execute(f"""create table if not exists evidence_chunks (
            tenant text not null, space text not null, chunk_id text not null, text text not null,
            meta jsonb not null, embedding vector({dim}) not null, primary key (tenant, space, chunk_id))""")
        self.emb = get_embedder()

    def upsert(self, chunks: list[Chunk], texts: list[str] | None = None) -> None:
        vecs = self.emb.embed(texts or [c.text for c in chunks], kind="doc")
        with self.conn.cursor() as cur:
            cur.execute("delete from evidence_chunks where tenant=%s and space=%s", (self.tenant, self.space))
            for c, v in zip(chunks, vecs, strict=True):
                cur.execute("insert into evidence_chunks values (%s,%s,%s,%s,%s,%s)",
                            (self.tenant, self.space, c.id, c.text, json.dumps(c.meta), v))

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        q = self.emb.embed([query], kind="query")[0]
        rows = self.conn.execute(
            "select chunk_id, 1 - (embedding <=> %s) as sim from evidence_chunks where tenant=%s and space=%s "
            "order by embedding <=> %s limit %s", (q, self.tenant, self.space, q, k)).fetchall()
        return [(r[0], float(r[1])) for r in rows]
