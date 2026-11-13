"""Explicit promotion rules (R7). The ONLY code path that writes promoted long-term memory.

Style rule: a pattern extracted from approved user edits is promoted when it occurred in at least
`memory.style_promotion.min_occurrences` edits across at least `min_distinct_jobs` different jobs, and it was
not deleted by the user before (tombstone). Edits produced by "regenerate paragraph" are not user edits and
are never observed.

Outcome rule: per job category, outcome statistics are promoted after `memory.outcome_promotion.min_outcomes`
real marketplace outcomes (reply / interview / hire / lost) — never from a single event or from tool output.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict
from typing import Any

from common.config import cfg

from .store import ns, observe

WATCH_WORDS = ["passionate", "hardworking", "hard-working", "expert", "guru", "ninja", "rockstar", "dear", "kindly",
               "synergy", "leverage", "cutting-edge", "world-class", "best", "perfect", "100%"]


def edit_patterns(before: str, after: str) -> list[str]:
    """Turn one edit into normalised, human-readable candidate rules."""
    pats: list[str] = []
    b_sents = re.split(r"(?<=[.!?])\s+", before.strip())
    a_sents = re.split(r"(?<=[.!?])\s+", after.strip())
    if len(b_sents) > 1 and a_sents and b_sents[0] not in after and b_sents[1][:40] in a_sents[0]:
        pats.append("Cut the first sentence: start directly with the client's problem.")
    bw, aw = Counter(re.findall(r"[a-z'-]+", before.lower())), Counter(re.findall(r"[a-z'-]+", after.lower()))
    for w in WATCH_WORDS:
        if bw[w] > 0 and aw[w] == 0:
            pats.append(f"Never use the word '{w}'.")
    lb, la = len(before.split()), len(after.split())
    if lb and la < 0.8 * lb:
        pats.append("Keep proposals shorter (the user trims about 20%+).")
    if re.search(r"(?i)\b(best|cheers|thanks),?\s*$", after) and not re.search(r"(?i)\b(best|cheers|thanks),?\s*$", before):
        pats.append(f"End with a short sign-off like '{after.strip().split()[-1]}'.")
    sm = difflib.SequenceMatcher(None, before.split(), after.split())
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and 1 <= i2 - i1 <= 3 and 1 <= j2 - j1 <= 3:
            old, new = " ".join(before.split()[i1:i2]), " ".join(after.split()[j1:j2])
            if old.lower().strip(".,") != new.lower().strip(".,"):
                pats.append(f"Prefer '{new.strip('.,')}' over '{old.strip('.,')}'.")
    return pats


async def record_edit(store: Any, user_id: str, job_id: str, before: str, after: str, source: str = "user") -> list[str]:
    """Stage observations from one approved edit, then apply the promotion rule. Returns newly promoted rules."""
    if store is None or source != "user" or before.strip() == after.strip():
        return []
    for p in edit_patterns(before, after):
        await observe(store, "style", user_id, {"pattern": p, "job_id": job_id})
    return await promote_style(store, user_id)


async def promote_style(store: Any, user_id: str) -> list[str]:
    rule = cfg("memory", "style_promotion")
    obs = await store.asearch(ns("style_obs", user_id), limit=1000)
    by_pat: dict[str, set] = defaultdict(set)
    counts: Counter = Counter()
    for o in obs:
        counts[o.value["pattern"]] += 1
        by_pat[o.value["pattern"]].add(o.value.get("job_id"))
    promoted = {i.key for i in await store.asearch(ns("style", user_id), limit=200)}
    tomb = {i.key for i in await store.asearch(ns("style_tombstone", user_id), limit=200)}
    new = []
    for pat, n in counts.most_common():
        key = re.sub(r"[^a-z0-9]+", "-", pat.lower())[:60]
        if key in promoted or key in tomb:
            continue
        if n >= rule["min_occurrences"] and len(by_pat[pat]) >= rule["min_distinct_jobs"] and len(promoted) < rule["max_items"]:
            await store.aput(ns("style", user_id), key, {"rule": pat, "evidence_edits": n, "jobs": len(by_pat[pat]),
                                                         "promoted_by": "style_promotion_rule_v1"})
            promoted.add(key)
            new.append(pat)
    return new


async def record_outcome(store: Any, user_id: str, category: str, event: str, cited_projects: list[str]) -> bool:
    """Stage a real marketplace outcome; promote category stats once enough outcomes exist."""
    if store is None or event not in {"replied", "interview", "hired", "lost", "submitted"}:
        return False
    await observe(store, "outcome", user_id, {"category": category, "event": event, "projects": cited_projects})
    obs = [o.value for o in await store.asearch(ns("outcome_obs", user_id), limit=2000) if o.value["category"] == category]
    real = [o for o in obs if o["event"] in {"replied", "interview", "hired", "lost"}]
    if len(real) < cfg("memory", "outcome_promotion", default={"min_outcomes": 3})["min_outcomes"]:
        return False
    submitted = sum(o["event"] == "submitted" for o in obs) or len(real)
    replied = sum(o["event"] in {"replied", "interview", "hired"} for o in obs)
    proj = Counter(p for o in obs if o["event"] in {"replied", "interview", "hired"} for p in o.get("projects", []))
    await store.aput(ns("outcome", user_id), category, {
        "category": category, "submitted": submitted, "replied": replied, "hired": sum(o["event"] == "hired" for o in obs),
        "top_projects": [p for p, _ in proj.most_common(3)], "promoted_by": "outcome_promotion_rule_v1"})
    return True
