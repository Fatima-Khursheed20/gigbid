"""Risk Assessor: client quality from marketplace history; scams, free-work requests, off-platform asks and
injected instructions. Deterministic rules always run; the small LLM adds judgement on top (llm+rules)."""

from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig

from common import llm
from common.config import cfg, prompt

from ..guards import delimit, detect_injection
from ..handoffs import RiskReport
from ._base import deps, node

RULES = {
    "off_platform_contact": r"(?i)\b(whatsapp|telegram|skype|signal)\b|add me on|contact me (on|at|via)",
    "off_platform_payment": r"(?i)\b(usdt|crypto|bitcoin|western union|paypal)\b.*\b(pay|payment|paid)|outside the platform to save fees",
    "unpaid_work": r"(?i)(for free as a (test|trial)|unpaid (trial|test)|complete the full working version for free)",
    "upfront_fee": r"(?i)(purchase|buy|pay for) (our|the) (onboarding|training|starter) kit|registration fee",
    "credential_request": r"(?i)(send|share) (us |me )?your (account )?(login|password|credentials)",
}
SCAM_FLAGS = {"off_platform_contact", "off_platform_payment", "unpaid_work", "upfront_fee", "credential_request",
              "too_good_to_be_true"}


def rule_report(job: dict, client: dict) -> RiskReport:
    text = f"{job['title']}\n{job['description']}"
    flags = [f for f, p in RULES.items() if re.search(p, text)]
    budget = job.get("budget") or 0
    if budget >= 1500 and re.search(r"(?i)(two hours|2 hours|no experience needed|copy-paste)", text):
        flags.append("too_good_to_be_true")
    h = (client or {}).get("history", {})
    if not h.get("payment_verified", True):
        flags.append("unverified_payment")
    if h.get("hires", 1) == 0 and h.get("total_spent", 1) == 0:
        flags.append("new_client")
    if h.get("jobs_posted", 0) >= 5 and h.get("hire_rate", 1) < 0.2:
        flags.append("low_hire_rate")
    spans = detect_injection(text)
    if spans:
        flags.append("prompt_injection")
    scam = bool(set(flags) & SCAM_FLAGS)
    quality = 0.5
    if h:
        quality = min(1.0, 0.25 + 0.25 * bool(h.get("payment_verified")) + 0.25 * min(1.0, (h.get("hires") or 0) / 10)
                      + 0.25 * ((h.get("avg_rating") or 3.5) - 3.0) / 2.0)
    score = min(1.0, (0.75 if scam else 0.0) + 0.1 * ("unverified_payment" in flags) + 0.1 * ("new_client" in flags)
                + 0.05 * ("low_hire_rate" in flags) + 0.05 * ("prompt_injection" in flags) + 0.2 * (1 - quality) * (not scam))
    return RiskReport(score=round(score, 3), scam=scam, flags=sorted(set(flags)), injection_detected=bool(spans),
                      injected_spans=spans, client_quality=round(max(0.0, quality), 3),
                      explanation="rule-based: " + (", ".join(sorted(set(flags))) or "no red flags"), source="heuristic")


async def assess(job: dict, client: dict) -> RiskReport:
    rules = rule_report(job, client)
    if not llm.available():
        return rules
    user = (f"Client history (from the marketplace API, trusted): {client.get('history')}\n"
            f"Rule-based pre-check flags: {rules.flags}\n\n" + delimit(f"{job['title']}\n\n{job['description']}"))
    try:
        r = await llm.structured("risk_assessor", prompt("risk_assessor"), user, RiskReport)
    except (llm.LLMUnavailable, Exception):  # noqa: BLE001 - malformed output -> rules only
        return rules
    # Rules are a floor: the LLM can add flags but cannot clear a rule hit (an injection can't talk it out).
    flags = sorted(set(r.flags) | set(rules.flags))
    scam = rules.scam or (r.scam and bool(set(r.flags) & SCAM_FLAGS))
    score = max(rules.score, r.score if scam else min(r.score, cfg("thresholds", "scam_risk", default=0.7) - 0.05))
    return RiskReport(score=round(score, 3), scam=scam, flags=flags, injection_detected=rules.injection_detected or r.injection_detected,
                      injected_spans=rules.injected_spans or r.injected_spans[:3], client_quality=rules.client_quality,
                      explanation=r.explanation[:500], source="llm+rules")


@node("risk_assessor", timeout_s=60)
async def risk_assessor(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    job = state["job"]
    client = await d.port.get_client_history("risk_assessor", job["client_id"])
    report = await assess(job, client)
    return {"risk": report.model_dump(), "client": client, "analyses_done": ["risk"]}
