"""Compliance Guard: enforce the policy pack. Removes contact details, guarantees and invented claims; blocks
with a reason shown in the UI when the draft cannot be fixed safely. Rules come from agent/config.yaml and the
marketplace's current policy (so a platform policy update is absorbed by configuration)."""

from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig

from common import llm
from common.config import cfg, prompt

from ..handoffs import ComplianceVerdict, Violation
from ._base import node


def check_text(text: str, policy: dict | None = None) -> ComplianceVerdict:
    c = cfg("compliance")
    policy = policy or {}
    checks = set(policy.get("submission_checks", []))
    violations: list[Violation] = []
    cleaned = text
    for rule, pats in c["banned_patterns"].items():
        for p in pats:
            for m in re.finditer(p, cleaned, flags=re.I):
                sent = _sentence_of(cleaned, m.start())
                violations.append(Violation(rule=rule, excerpt=m.group(0), fix="removed sentence"))
                cleaned = cleaned.replace(sent, "")
    for p in c.get("fabricated_experience", []):
        for m in re.finditer(p, cleaned, flags=re.I):
            violations.append(Violation(rule="fabricated_experience", excerpt=m.group(0), fix="removed sentence"))
            cleaned = cleaned.replace(_sentence_of(cleaned, m.start()), "")
    forbid_urls = c.get("forbid_urls") or "no_external_urls" in checks
    if forbid_urls:
        for m in re.finditer(r"https?://\S+", cleaned):
            violations.append(Violation(rule="external_url", excerpt=m.group(0), fix="removed link"))
            cleaned = cleaned.replace(m.group(0), "")
    required = list(c.get("required_lines") or [])
    if "ai_disclosure" in checks:
        required.append("Drafted with AI assistance and reviewed by me.")
    for line in required:
        if line.lower() not in cleaned.lower():
            violations.append(Violation(rule="required_line", excerpt=line, fix="appended"))
            cleaned = cleaned.rstrip() + "\n\n" + line
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    words = len(re.sub(r"\[E\d+\]", "", cleaned).split())
    blocked = words < 30
    reason = "Draft too short after removing policy violations; regenerate or edit." if blocked else ""
    return ComplianceVerdict(ok=not violations, blocked=blocked, violations=violations, cleaned_text=cleaned,
                             policy_version=policy.get("version", c.get("policy_version", "v1")), reason=reason)


def _sentence_of(text: str, idx: int) -> str:
    start = max(text.rfind(". ", 0, idx), text.rfind("\n", 0, idx))
    end_candidates = [i for i in (text.find(". ", idx), text.find("\n", idx)) if i != -1]
    end = min(end_candidates) + 1 if end_candidates else len(text)
    return text[start + 1 if start >= 0 else 0:end].strip()


async def llm_check(text: str, policy: dict) -> list[Violation]:
    if not llm.available():
        return []
    from pydantic import BaseModel

    class _V(BaseModel):
        violations: list[Violation] = []

    try:
        r = await llm.structured("compliance", prompt("compliance"),
                                 f"POLICY RULES:\n{policy.get('rules')}\n\nTEXT:\n{text}", _V, max_tokens=500)
        return [v for v in r.violations if v.excerpt and v.excerpt in text]
    except Exception:  # noqa: BLE001
        return []


@node("compliance", timeout_s=60)
async def compliance(state: dict, config: RunnableConfig) -> dict:
    policy = state.get("policy") or {}
    draft = dict(state["draft"])
    verdict = check_text(draft["cover_letter"], policy)
    extra = await llm_check(verdict.cleaned_text or "", policy)
    if extra:  # the LLM found something the rules missed: remove the offending sentence, block only if unfixable
        text = verdict.cleaned_text or ""
        for v in extra:
            sent = _sentence_of(text, text.find(v.excerpt)) if v.excerpt in text else ""
            if sent:
                text = text.replace(sent, "")
                v.fix = "removed sentence"
        verdict.violations += extra
        verdict.cleaned_text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", text)).strip()
        if len(re.sub(r"\[E\d+\]", "", verdict.cleaned_text).split()) < 30:
            verdict.blocked = True
            verdict.reason = "Compliance model flagged: " + "; ".join(v.rule for v in extra)[:200]
        verdict.ok = False
    answers = []
    for a in draft.get("screening_answers", []):
        v = check_text(a["answer"], {**policy, "submission_checks": [c for c in policy.get("submission_checks", [])
                                                                     if c != "ai_disclosure"]})
        verdict.violations += v.violations
        answers.append({"question": a["question"], "answer": v.cleaned_text or ""})
    draft.update(cover_letter=verdict.cleaned_text, screening_answers=answers)
    status = "blocked" if verdict.blocked else "awaiting_approval"
    return {"draft": draft, "compliance": verdict.model_dump(), "status": status,
            "attention": verdict.reason if verdict.blocked else None}
