"""Request/response models. The web client's TypeScript types are generated from these via OpenAPI."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Email = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Ok(BaseModel):
    ok: bool = True
    detail: str | None = None


class RegisterIn(BaseModel):
    email: str = Email
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: str = Email
    password: str


class Me(BaseModel):
    id: str
    email: str
    name: str
    is_reviewer: bool = False
    tenant: str | None = None
    persona: str | None = None
    hourly_rate: float | None = None
    floor_rate: float | None = None
    min_project: float | None = None
    weekly_connects_budget: int | None = None
    autonomy: str | None = None
    categories: list[str] = []
    marketplace_mode: str | None = None
    onboarded: bool = False
    connected: list[str] = []


class AuthOut(BaseModel):
    token: str
    user: Me


class ProfileIn(BaseModel):
    persona: Literal["ai_ml", "fullstack", "data_analyst", "own"] | None = None
    hourly_rate: float | None = Field(default=None, gt=0, le=1000)
    floor_rate: float | None = Field(default=None, gt=0, le=1000)
    min_project: float | None = Field(default=None, ge=0, le=100000)
    weekly_connects_budget: int | None = Field(default=None, ge=0, le=1000)
    autonomy: Literal["suggest", "auto_skip_low_fit"] | None = None
    categories: list[str] | None = None
    onboarded: bool | None = None


class ConnectIn(BaseModel):
    provider: Literal["gigsim"]
    token: str = Field(min_length=4, max_length=200)


class SearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    query: str = ""
    category: Literal["", "ai_ml", "web", "data", "other"] = ""
    pool: Literal["", "dev", "stream", "heldout"] = ""
    interval_minutes: int = Field(default=30, ge=10, le=1440)


class SavedSearch(SearchIn):
    id: int
    enabled: bool = True
    last_run_at: str | None = None


class InboxItem(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    fit: float | None = None
    risk: float | None = None
    scam: bool | None = None
    injection: bool | None = None
    action: str | None = None
    price: float | None = None
    bid_type: str | None = None
    connects: int | None = None
    status: str
    summary: dict[str, Any] | None = None
    updated_at: str | None = None


class JobDetail(BaseModel):
    job: dict[str, Any]
    status: str | None = None
    job_spec: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    fit: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    price: dict[str, Any] | None = None
    client: dict[str, Any] | None = None
    thread_id: str
    has_pending_approval: bool = False
    attention: str | None = None
    degraded: dict[str, Any] | None = None


class RunRef(BaseModel):
    run_id: str
    status: str = "queued"


class Decision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(default=None, max_length=6000)
    reason: str | None = Field(default=None, max_length=500)


class Studio(BaseModel):
    job_id: str
    thread_id: str
    pending: bool
    status: str | None = None
    payload: dict[str, Any] | None = None
    submission: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []


class RegenerateIn(BaseModel):
    paragraph_index: int = Field(ge=0, le=10)
    instruction: str = Field(default="", max_length=300)


class RegenerateOut(BaseModel):
    paragraph: str
    cover_letter: str


class Run(BaseModel):
    id: str
    kind: str
    thread_id: str
    job_id: str | None = None
    status: str
    started_at: str
    ended_at: str | None = None
    latency_s: float | None = None
    tokens: int | None = None
    usd: float | None = None
    by_node: dict[str, Any] | None = None
    trace_id: str | None = None
    trace_url: str | None = None
    error: str | None = None


class RunDetail(Run):
    events: list[dict[str, Any]] = []


class Checkpoint(BaseModel):
    checkpoint_id: str
    next: list[str]
    step: int | None = None
    created_at: str | None = None
    status: str | None = None


class PipelineCard(BaseModel):
    proposal_id: str
    job_id: str
    title: str | None = None
    stage: str
    category: str | None = None
    amount: float | None = None
    connects: int | None = None
    updated_at: str | None = None


class Thread(BaseModel):
    thread_id: str
    job_id: str | None = None
    status: str | None = None
    intent: str | None = None
    last_message: str | None = None
    n: int | None = None


class ThreadDetail(BaseModel):
    thread_id: str
    messages: list[dict[str, Any]]
    pending: bool
    payload: dict[str, Any] | None = None
    status: str | None = None


class Analytics(BaseModel):
    by_category: list[dict[str, Any]]
    connects: dict[str, Any]
    cost_latency: dict[str, Any]
    rejection_reasons: list[dict[str, Any]]
    funnel: dict[str, int]


class MemoryOut(BaseModel):
    style: list[dict[str, Any]]
    outcome: list[dict[str, Any]]


class Health(BaseModel):
    api: str
    db: str
    redis: str
    marketplace: str
    portfolio: str
    llm: str
    marketplace_mode: str
    model_profile: str
    degraded: bool
