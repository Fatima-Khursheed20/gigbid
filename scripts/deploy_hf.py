"""Deploy GigBid to a public Hugging Face Docker Space.

    python -m scripts.deploy_hf            # creates/updates <hf-user>/gigbid, sets secrets, uploads code
Secrets are set server-side through the HF API and never written to the repo. Reviewer credentials are
generated once and stored locally in data/processed/reviewer_credentials.json (git-ignored) so they can be
shared privately with the grader.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / "data" / "processed" / "reviewer_credentials.json"
SPACE_README = """---
title: GigBid
emoji: 🤝
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent freelancer copilot (LangGraph, MCP, RAG)
---

# GigBid — live demo

Multi-agent freelancer copilot: LangGraph agents find jobs on **GigSim** (a marketplace simulator with synthetic
data), judge them, draft evidence-grounded proposals and wait for **your approval** before anything is sent.

Source code, architecture, evaluation results and setup: https://github.com/Fatima-Khursheed20/gigbid

All data here is synthetic. Postgres and Redis run inside this container, so state resets when the Space restarts.
"""
IGNORE = [".venv/*", "**/node_modules/*", "apps/web/dist/*", ".cache/*", "data/processed/*", "data/heldout/*",
          "data/raw/*", "data/tenants/*", ".env", ".git/*", "**/__pycache__/*", "apps/web/test-results/*",
          "apps/web/playwright-report/*", "*.db", "*.sqlite", "README.md"]


def main() -> None:
    env = dotenv_values(ROOT / ".env")
    api = HfApi(token=env["HF_TOKEN"])
    user = api.whoami()["name"]
    repo = f"{user}/gigbid"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
    if CREDS.exists():
        creds = json.loads(CREDS.read_text())
    else:
        creds = {"email": "reviewer@gigbid.app", "password": secrets.token_urlsafe(12)}
        CREDS.parent.mkdir(parents=True, exist_ok=True)
        CREDS.write_text(json.dumps(creds, indent=1))
    for k, v in {"GROQ_API_KEY": env["GROQ_API_KEY"], "APP_SECRET_KEY": secrets.token_urlsafe(40),
                 "MCP_MARKETPLACE_TOKEN": secrets.token_urlsafe(24), "GIGSIM_ADMIN_TOKEN": secrets.token_urlsafe(24),
                 "REVIEWER_EMAIL": creds["email"], "REVIEWER_PASSWORD": creds["password"],
                 **({"LANGSMITH_API_KEY": env["LANGSMITH_API_KEY"]} if env.get("LANGSMITH_API_KEY") else {})}.items():
        api.add_space_secret(repo, k, v)
    for k, v in {"MODEL_PROFILE": "open", "MARKETPLACE_MODE": "gigsim", "LLM_CONCURRENCY": "2",
                 "LANGSMITH_TRACING": "true" if env.get("LANGSMITH_API_KEY") else "false"}.items():
        api.add_space_variable(repo, k, v)
    api.upload_folder(folder_path=str(ROOT), repo_id=repo, repo_type="space", ignore_patterns=IGNORE,
                      commit_message="Deploy GigBid")
    api.upload_file(path_or_fileobj=SPACE_README.encode(), path_in_repo="README.md", repo_id=repo, repo_type="space",
                    commit_message="Space card")
    sub = repo.replace("/", "-").lower()
    print(json.dumps({"space": f"https://huggingface.co/spaces/{repo}", "app": f"https://{sub}.hf.space"}))


if __name__ == "__main__":
    main()
