"""V4 — outcome-aware ranking (ranking group): boost evidence/phrasing from proposals that won or got replies."""
from ..pipeline import Settings

SETTINGS = Settings(name="v4_outcome", query="decomposed", hybrid=True, rerank=True, outcome=True)
