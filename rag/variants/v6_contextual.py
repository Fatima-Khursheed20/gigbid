"""V6 — contextual retrieval (indexing group): a generated context line is prepended to each chunk before
embedding and BM25 indexing. Context lines come from scripts/build_context_lines.py (LLM) when present,
else from a metadata template (reported separately)."""
from ..pipeline import Settings

SETTINGS = Settings(name="v6_contextual", query="decomposed", hybrid=True, rerank=True, contextual=True)
