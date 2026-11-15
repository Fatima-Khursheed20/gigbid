"""Download the open embedding + reranker models and pre-embed every persona corpus into the vector cache."""

from __future__ import annotations

from mcp_servers.portfolio.tools import STORE
from rag.index.embeddings import get_reranker
from rag.pipeline import Query
from rag.retriever import make

if __name__ == "__main__":
    get_reranker()
    for tenant in ("ai_ml", "fullstack", "data_analyst"):
        c = STORE.corpus(tenant)
        _ = c.dense, c.bm25, c.naive_dense
        make(c, "v5_multivector").retrieve(Query(job_text="warm up", requirements=["warm up"]))
        print("warmed", tenant, len(c.chunks), "chunks")
