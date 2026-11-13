"""V5 — multi-vector items (indexing group): summary, README and code chunks indexed separately and
returned as one project item, so repos that look irrelevant from their README alone still surface."""
from ..pipeline import Settings

SETTINGS = Settings(name="v5_multivector", query="decomposed", hybrid=True, rerank=True, multivector=True)
