"""V0 — naive dense baseline (required): fixed 400-char chunks, top-k cosine on the whole job post."""
from ..pipeline import Settings

SETTINGS = Settings(name="v0_naive", chunking="fixed", query="whole")
