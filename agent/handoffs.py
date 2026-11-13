"""Structured hand-offs (C3): agents exchange these Pydantic objects, never free text, for anything a later
step decides on."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    text: str
    skill: str | None = Field(default=None, description="Canonical tool/skill if one is named or clearly implied")
    must_have: bool = True


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str = "other"
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    budget_type: Literal["fixed", "hourly"] = "fixed"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline_weeks: float | None = None
    est_hours: float | None = Field(default=None, description="Effort estimate in hours")
    complexity: Literal["small", "medium", "large"] = "medium"
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="Needs implied but not stated")
    source: Literal["llm", "heuristic"] = "llm"


RiskFlag = Literal["off_platform_contact", "off_platform_payment", "unpaid_work", "upfront_fee", "credential_request",
                   "too_good_to_be_true", "prompt_injection", "unverified_payment", "new_client", "low_hire_rate",
                   "low_budget", "vague_scope"]


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1, description="0 = safe, 1 = certain scam/abuse")
    scam: bool = False
    flags: list[RiskFlag] = Field(default_factory=list)
    injection_detected: bool = False
    injected_spans: list[str] = Field(default_factory=list)
    client_quality: float = Field(default=0.5, ge=0, le=1)
    explanation: str = ""
    source: Literal["llm", "heuristic", "llm+rules"] = "llm+rules"


class EvidenceRef(BaseModel):
    evidence_id: str
    project_id: str | None = None
    project: str | None = None
    type: str | None = None
    snippet: str = ""
    score: float = 0.0


class RequirementEvidence(BaseModel):
    requirement: str
    status: Literal["supported", "weak", "none"]
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matrix: list[RequirementEvidence] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["skip", "watch", "bid"]
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)


class PriceQuote(BaseModel):
    bid_type: Literal["fixed", "hourly"]
    amount: float = Field(gt=0)
    band_low: float
    band_high: float
    market_hourly_p50: float | None = None
    est_hours: float | None = None
    connects_cost: int = 0
    connects_worth_it: bool = True
    rationale: str = ""


class ClaimCheck(BaseModel):
    claim: str
    label: Literal["supported", "partly_supported", "unsupported"]
    evidence_ids: list[str] = Field(default_factory=list)
    action: Literal["kept", "rewritten", "removed"] = "kept"
    note: str = ""


class ScreeningAnswer(BaseModel):
    question: str
    answer: str


class ProposalDraft(BaseModel):
    job_id: str
    cover_letter: str
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[ClaimCheck] = Field(default_factory=list)
    version: int = 1
    word_count: int = 0


class CritiqueIssue(BaseModel):
    kind: Literal["grounding", "personalisation", "length", "generic_opening", "tone", "screening", "other"]
    detail: str


class Critique(BaseModel):
    approve: bool
    issues: list[CritiqueIssue] = Field(default_factory=list)
    revision_instructions: str = ""
    round: int = 0
    score: float = Field(default=0.5, ge=0, le=1)


class Violation(BaseModel):
    rule: str
    excerpt: str
    fix: str = ""


class ComplianceVerdict(BaseModel):
    ok: bool
    blocked: bool = False
    violations: list[Violation] = Field(default_factory=list)
    cleaned_text: str | None = None
    policy_version: str = "v1"
    reason: str = ""


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None
    user_id: str | None = None


class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    injection_detected: bool = False
    summary: str = ""
    asks: list[str] = Field(default_factory=list)


class ReplyDraft(BaseModel):
    body: str
    proposed_slots: list[dict] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
