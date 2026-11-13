"""Decision node: skip / watch / bid from the three parallel analyses. Thresholds come from config."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from common.config import cfg

from ..handoffs import BidDecision
from ._base import deps, node


def decide_from(spec: dict, risk: dict, fit: dict, job: dict, profile) -> BidDecision:
    t = cfg("thresholds")
    reasons: list[str] = []
    if risk.get("scam") or risk.get("score", 0) >= t["scam_risk"]:
        flags = [f for f in risk.get("flags", []) if f != "prompt_injection"]
        return BidDecision(action="skip", reasons=[f"Risk: likely scam ({', '.join(flags) or 'high risk score'})"],
                           confidence=0.9)
    budget = job.get("budget")
    hr = job.get("hourly_range")
    if job.get("budget_type") == "fixed" and budget is not None and budget < profile.min_project:
        return BidDecision(action="skip", reasons=[f"Budget ${budget:.0f} is below your minimum project ${profile.min_project:.0f}"],
                           confidence=0.85)
    if job.get("budget_type") == "hourly" and hr and hr[1] < profile.floor_rate:
        return BidDecision(action="skip", reasons=[f"Max rate ${hr[1]}/h is below your floor ${profile.floor_rate}/h"],
                           confidence=0.85)
    f = fit.get("score", 0.0)
    reasons += fit.get("reasons", [])
    if risk.get("injection_detected"):
        reasons.append("Job post contains instruction-like text aimed at AI tools (ignored).")
    if f < t["watch_min_fit"]:
        return BidDecision(action="skip", reasons=[f"Low fit {f:.2f}"] + reasons, confidence=0.7)
    if f < t["bid_min_fit"] or risk.get("score", 0) > t["max_risk_to_bid"]:
        return BidDecision(action="watch", reasons=[f"Borderline fit {f:.2f} / risk {risk.get('score', 0):.2f}"] + reasons,
                           confidence=0.5)
    return BidDecision(action="bid", reasons=[f"Fit {f:.2f}, risk {risk.get('score', 0):.2f}"] + reasons,
                       confidence=min(0.95, 0.5 + f / 2))


@node("decide", timeout_s=10)
async def decide(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    dec = decide_from(state.get("job_spec", {}), state.get("risk", {}), state.get("fit", {}), state["job"], d.profile)
    status = {"skip": "skipped", "watch": "watch", "bid": "drafting"}[dec.action]
    return {"decision": dec.model_dump(), "status": status}
