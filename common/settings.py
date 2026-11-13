"""Environment-driven settings. Secrets only ever come from environment variables (.env locally)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "dev-insecure-secret-change-me"
    token_encryption_key: str = ""
    database_url: str = ""
    redis_url: str = ""

    marketplace_mode: str = ""
    gigsim_base_url: str = "http://localhost:8081"
    gigsim_admin_token: str = "gigsim-admin"

    mcp_portfolio_url: str = "http://localhost:8101/mcp"
    mcp_marketplace_url: str = "http://localhost:8102/mcp"
    mcp_workspace_url: str = "http://localhost:8103/mcp"
    mcp_marketplace_token: str = "dev-marketplace-token"

    model_profile: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    llm_offline: bool = False

    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "gigbid"

    github_mcp_url: str = "https://api.githubcopilot.com/mcp/"
    github_personal_access_token: str = ""
    upwork_mcp_url: str = "https://mcp.upwork.com/mcp"
    upwork_oauth_redirect_url: str = "http://localhost:8000/api/auth/upwork/callback"

    reviewer_email: str = ""
    reviewer_password: str = ""
    web_dist: str = str(ROOT / "apps" / "web" / "dist")
    data_dir: str = str(ROOT / "data")


@lru_cache
def get_settings() -> Settings:
    return Settings()
