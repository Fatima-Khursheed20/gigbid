"""V3 — cross-encoder reranking (retrieval group, required) on top of V2's candidates: precision at small k."""
from ..pipeline import Settings

SETTINGS = Settings(name="v3_rerank", query="decomposed", hybrid=True, rerank=True)
