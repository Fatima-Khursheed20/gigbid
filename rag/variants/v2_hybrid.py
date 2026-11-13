"""V2 — hybrid BM25 + dense with reciprocal rank fusion (retrieval group, required).
Targets exact tool names ("Celery", "dbt", "Pinecone") that embeddings blur."""
from ..pipeline import Settings

SETTINGS = Settings(name="v2_hybrid", query="decomposed", hybrid=True)
