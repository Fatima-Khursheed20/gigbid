"""Shared test setup: offline LLM, no chaos errors, no external DB unless a test opts in."""

import os

os.environ.setdefault("LLM_OFFLINE", "1")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("WORKSPACE_DB", ":memory:")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
