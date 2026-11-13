"""Claim verification (B3, R5): split a draft into claims, label each against the evidence the writer saw,
remove or rewrite unsupported claims BEFORE the Critic sees the draft, and report the unsupported-claim rate
before and after verification."""

from __future__ import annotations

import re

from pydantic import BaseModel

from common import llm
from common.config import prompt

CLAIM_HINT = re.compile(r"(?i)\b(i|i've|i'm|my|we|our)\b.*\b(built|shipped|delivered|led|designed|created|developed|"
                        r"reduced|cut|increased|improved|migrated|deployed|trained|automated|worked|have|has|years?|"
                        r"experience|helped|launched|made|ran|set up|moved)\b")
CITE = re.compile(r"\[E(\d+)\]")
NUM = re.compile(r"\d+(?:[.,]\d+)?")


class _Claims(BaseModel):
    claims: list[dict]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


EXTRA_TECH = ["Kubernetes", "Terraform", "Kafka", "Spark", "Hadoop", "GCP", "Google Cloud", "Azure", "AWS", "Lambda",
              "Vertex AI", "Databricks", "Elasticsearch", "OpenSearch", "Weaviate", "Qdrant", "Chroma", "Milvus",
              "TensorFlow", "Keras", "JAX", "Ray", "Vue", "Angular", "Svelte", "Laravel", "Flask", "Rails", "Go",
              "Rust", "Java", "Kotlin", "Swift", "Firebase", "Supabase", "Looker", "Qlik", "SAS", "SPSS", "Hive",
              "Redshift", "Kinesis", "Grafana", "Prometheus", "Jenkins", "GitLab", "Ansible", "OpenAI", "GPT-4",
              "Claude", "Llama", "Mistral", "Gemini", "vLLM", "Ollama", "Neo4j", "Cassandra", "DynamoDB", "Heroku"]


def _named_tech(text: str) -> set[str]:
    from .skills import ALIASES

    found = set()
    for name in list(ALIASES) + EXTRA_TECH:
        if len(name) > 2 and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, flags=re.I):
            found.add(name.lower())
    return found


def unsupported_tech(claim: str, evidence_texts: list[str]) -> list[str]:
    """Deterministic grounding check: every technology NAMED in a claim must appear in the evidence it cites
    (catches the classic "Docker and Kubernetes" overreach that LLM verifiers wave through)."""
    ev = " ".join(evidence_texts).lower()
    from .skills import ALIASES

    missing = []
    for t in _named_tech(claim):
        canon = next((k for k in ALIASES if k.lower() == t), None)
        aliases = [a.lower().strip() for a in ALIASES.get(canon, [])] if canon else []
        if t not in ev and not any(len(a) > 3 and a in ev for a in aliases):
            missing.append(t)
    return missing


def heuristic_verify(text: str, evidence: list[dict]) -> list[dict]:
    """Offline verifier: a claim is supported if it cites evidence and its numbers appear in that evidence."""
    out = []
    for s in split_sentences(text):
        if not CLAIM_HINT.search(s):
            continue
        cites = [int(n) for n in CITE.findall(s)]
        ev = [evidence[n - 1] for n in cites if 0 < n <= len(evidence)]
        nums = set(NUM.findall(CITE.sub("", s)))
        ev_text = " ".join(e.get("text", "") for e in ev)
        if not ev:
            label = "unsupported"
        elif nums and not nums <= set(NUM.findall(ev_text)):
            label = "partly_supported"
        else:
            label = "supported"
        if label == "supported" and unsupported_tech(CITE.sub("", s), [e.get("text", "") for e in ev]):
            label = "partly_supported"
        out.append({"claim": s, "label": label, "evidence_ids": [e["evidence_id"] for e in ev], "note": ""})
    return out


async def label_claims(text: str, evidence: list[dict]) -> list[dict]:
    if not llm.available():
        return heuristic_verify(text, evidence)
    ev = "\n".join(f"[E{i + 1}] ({e.get('type')}, {e.get('project')}) {e.get('text', '')[:700]}" for i, e in enumerate(evidence))
    try:
        res = await llm.structured("verifier", prompt("verifier"), f"EVIDENCE:\n{ev}\n\nPROPOSAL:\n{text}", _Claims,
                                   max_tokens=1500)
    except Exception:  # noqa: BLE001 - verifier failure must not let claims through unchecked
        return heuristic_verify(text, evidence)
    out = []
    by_id = {e["evidence_id"]: e for e in evidence}
    all_ev = [e.get("text", "") for e in evidence]
    for c in res.claims:
        lab = c.get("label", "unsupported")
        if lab not in ("supported", "partly_supported", "unsupported"):
            lab = "unsupported"
        ids = []
        for x in c.get("evidence_ids") or []:
            m = re.match(r"E?(\d+)$", str(x).strip("[] "))
            if m and 0 < int(m.group(1)) <= len(evidence):
                ids.append(evidence[int(m.group(1)) - 1]["evidence_id"])
            elif any(e["evidence_id"] == x for e in evidence):
                ids.append(x)
        claim, note = c.get("claim", ""), c.get("note", "") or ""
        missing = unsupported_tech(claim, [by_id[i].get("text", "") for i in ids] or all_ev)
        if missing and lab == "supported":
            lab, note = "partly_supported", ""  # remove rather than trust an LLM rewrite of an overreach
        out.append({"claim": claim, "label": lab, "evidence_ids": ids, "note": note,
                    "tech_not_in_evidence": missing})
    return out


def _closest_sentence(text: str, claim: str, min_overlap: float = 0.5) -> str | None:
    words = set(re.findall(r"[a-z0-9]{3,}", claim.lower()))
    best, score = None, 0.0
    for s in split_sentences(text):
        sw = set(re.findall(r"[a-z0-9]{3,}", s.lower()))
        if not sw or not words:
            continue
        ov = len(words & sw) / len(words)
        if ov > score:
            best, score = s, ov
    return best if score >= min_overlap else None


def apply_labels(text: str, claims: list[dict]) -> tuple[str, list[dict]]:
    """Remove unsupported claims; rewrite partly supported ones with the verifier's grounded note."""
    new = text
    for c in claims:
        claim = c["claim"].strip()
        if claim and claim not in new and c["label"] != "supported":
            claim = _closest_sentence(new, claim) or claim  # LLMs paraphrase claims; act on the real sentence
        if not claim or claim not in new:
            c["action"] = "kept"
            continue
        if c["label"] == "unsupported":
            if c.get("note"):
                new, c["action"] = new.replace(claim, c["note"]), "rewritten"
            else:
                new, c["action"] = new.replace(claim, ""), "removed"
        elif c["label"] == "partly_supported" and c.get("note"):
            new, c["action"] = new.replace(claim, c["note"]), "rewritten"
        elif c["label"] == "partly_supported" and c.get("tech_not_in_evidence"):
            fixed = claim
            for t in c["tech_not_in_evidence"]:
                fixed = re.sub(rf"(,\s*|\s+and\s+|\s+or\s+)?{re.escape(t)}", "", fixed, flags=re.I)
            new, c["action"] = new.replace(claim, fixed), "rewritten"
        else:
            c["action"] = "kept"
    new = re.sub(r"[ \t]{2,}", " ", new)
    new = re.sub(r"\n{3,}", "\n\n", new).strip()
    return new, claims


def rate(claims: list[dict]) -> dict:
    n = len(claims)
    u = sum(c["label"] == "unsupported" for c in claims)
    p = sum(c["label"] == "partly_supported" for c in claims)
    return {"claims": n, "unsupported": u, "partly_supported": p, "unsupported_rate": round(u / n, 3) if n else 0.0}


async def verify_claims(draft: str, evidence: list[dict]) -> dict:
    """Full B3 step. Returns cleaned text, labelled claims and before/after unsupported rates."""
    before = await label_claims(draft, evidence)
    cleaned, labelled = apply_labels(draft, [dict(c) for c in before])
    changed = cleaned != draft
    after = await label_claims(cleaned, evidence) if changed else before
    return {"text": cleaned, "claims": labelled, "before": rate(before), "after": rate(after), "changed": changed}
