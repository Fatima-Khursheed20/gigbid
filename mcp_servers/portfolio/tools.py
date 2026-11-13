"""Portfolio tool implementations and their schemas (read-only)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from common.config import cfg
from common.settings import ROOT
from rag.corpus import Corpus
from rag.pipeline import Query
from rag.retriever import make
from rag.variants.v8_crag import CragRetriever

TENANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class EvidenceFilters(BaseModel):
    types: list[str] | None = Field(default=None, description="Restrict to evidence types: cv, case_study, readme, "
                                                                "code, review, proposal")
    outcome: str | None = Field(default=None, pattern="^(won|replied|ignored)$",
                                description="Only past proposals with this outcome")
    min_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$", description="Only evidence dated >= YYYY-MM")
    project_id: str | None = Field(default=None, description="Only evidence about this project")


class EvidenceItem(BaseModel):
    evidence_id: str
    project_id: str | None
    project: str | None
    type: str | None
    source: str
    date: str | None
    outcome: str | None
    client_industry: str | None
    skills: list[str]
    score: float
    text: str


class SearchResult(BaseModel):
    tenant: str
    variant: str
    items: list[EvidenceItem]


class CaseStudy(BaseModel):
    id: str
    title: str | None
    client: str | None
    industry: str | None
    date: str | None
    skills: list[str]
    text: str


class SkillEntry(BaseModel):
    skill: str
    evidence_count: int
    projects: list[str]


class SkillList(BaseModel):
    tenant: str
    skills: list[SkillEntry]


class RequirementRow(BaseModel):
    requirement: str
    status: str = Field(description="supported | weak | none")
    best_score: float
    evidence: list[EvidenceItem]


class RequirementMatrix(BaseModel):
    tenant: str
    rows: list[RequirementRow]
    refuse: bool = Field(description="True when most requirements have no evidence (do not claim them)")


class PortfolioStore:
    """Per-tenant corpora, rebuilt when the tenant's files change (incremental re-index on upload)."""

    def __init__(self) -> None:
        self._corpora: dict[str, tuple[float, Corpus]] = {}

    def root_for(self, tenant: str) -> Path:
        single = os.environ.get("PORTFOLIO_DIR")
        if single:
            return Path(single)
        if not TENANT_RE.match(tenant):
            raise ValueError("invalid tenant id")
        own = Path(os.environ.get("TENANTS_DIR", ROOT / "data" / "tenants")) / tenant
        if own.exists():
            return own
        persona = Path(os.environ.get("PORTFOLIO_ROOT", ROOT / "data" / "personas")) / tenant
        if persona.exists():
            return persona
        raise FileNotFoundError(f"no portfolio for tenant {tenant!r}")

    @staticmethod
    def _stamp(root: Path) -> float:
        return max((p.stat().st_mtime for p in root.rglob("*") if p.is_file()), default=0.0)

    def corpus(self, tenant: str) -> Corpus:
        root = self.root_for(tenant)
        stamp = self._stamp(root)
        hit = self._corpora.get(tenant)
        if hit and hit[0] == stamp:
            return hit[1]
        c = Corpus(root, tenant)
        self._corpora[tenant] = (stamp, c)
        return c


STORE = PortfolioStore()


def _apply_filters(items: list[dict], f: EvidenceFilters | None) -> list[dict]:
    if not f:
        return items
    out = []
    for e in items:
        if f.types and e.get("type") not in f.types:
            continue
        if f.outcome and e.get("outcome") != f.outcome:
            continue
        if f.min_date and (e.get("date") or "0000") < f.min_date:
            continue
        if f.project_id and e.get("project_id") != f.project_id:
            continue
        out.append(e)
    return out


def search_evidence(tenant: str, requirement: str, k: int = 5, filters: EvidenceFilters | None = None,
                    variant: str | None = None) -> SearchResult:
    corpus = STORE.corpus(tenant)
    v = variant or cfg("rag", "variant", default="v3_rerank")
    retr = make(corpus, v)
    if isinstance(retr, CragRetriever):
        items = retr.retrieve(Query(job_text=requirement, requirements=[requirement]), k=k)
    else:
        items = retr.retrieve(Query(job_text=requirement, requirements=[requirement]), k=k)
    items = _apply_filters(items, filters)[:k]
    return SearchResult(tenant=tenant, variant=v, items=[EvidenceItem(**{f: e.get(f) for f in EvidenceItem.model_fields
                                                                       if f in e} | {"skills": e.get("skills") or []})
                                                         for e in items])


def requirement_matrix(tenant: str, requirements: list[str]) -> RequirementMatrix:
    corpus = STORE.corpus(tenant)
    res = CragRetriever(corpus).run(Query(job_text=" ".join(requirements), requirements=requirements))
    rows = []
    for m in res["matrix"]:
        ev = [EvidenceItem(**{f: e.get(f) for f in EvidenceItem.model_fields if f in e} | {"skills": e.get("skills") or []})
              for e in m["evidence"]]
        rows.append(RequirementRow(requirement=m["requirement"], status=m["status"], best_score=m["best_score"],
                                   evidence=ev))
    return RequirementMatrix(tenant=tenant, rows=rows, refuse=res["refuse"])


def get_case_study(tenant: str, case_id: str) -> CaseStudy:
    corpus = STORE.corpus(tenant)
    for d in corpus.docs:
        if d.type == "case_study" and (d.meta.get("project_id") == case_id or d.id.endswith(case_id)):
            from rag.skills import extract_skills

            return CaseStudy(id=d.meta.get("project_id") or case_id, title=d.meta.get("project"), client=d.meta.get("client"),
                             industry=d.meta.get("client_industry"), date=d.meta.get("date"),
                             skills=extract_skills(d.text), text=d.text)
    raise KeyError(f"case study {case_id!r} not found")


def get_proposal(tenant: str, proposal_id: str) -> dict:
    corpus = STORE.corpus(tenant)
    for d in corpus.docs:
        if d.type == "proposal" and d.id.endswith(proposal_id):
            return {"id": proposal_id, "text": d.text, **{k: d.meta.get(k) for k in ("outcome", "job_title", "date",
                                                                                    "cited_project_ids")}}
    raise KeyError(f"proposal {proposal_id!r} not found")


def list_skills(tenant: str) -> SkillList:
    corpus = STORE.corpus(tenant)
    agg: dict[str, dict] = {}
    for c in corpus.chunks:
        for s in c.meta.get("skills", []):
            a = agg.setdefault(s, {"n": 0, "projects": set()})
            a["n"] += 1
            if c.meta.get("project_id"):
                a["projects"].add(c.meta["project_id"])
    entries = [SkillEntry(skill=s, evidence_count=a["n"], projects=sorted(a["projects"]))
               for s, a in sorted(agg.items(), key=lambda kv: -kv[1]["n"])]
    return SkillList(tenant=tenant, skills=entries)


def profile(tenant: str) -> dict:
    import json

    p = STORE.root_for(tenant) / "profile.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"tenant": tenant}
