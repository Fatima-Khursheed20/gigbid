"""Loaders for a freelancer portfolio directory (B1).

Layout (persona corpora and user uploads share it):
  profile.json            optional: name, headline, rates
  projects.json           optional: project catalog (id, title, client, industry, date) for metadata
  cv.pdf | cv.md          CV
  case_studies/*.md       case studies (file stem = project id unless front-matter says otherwise)
  repos/<repo>/           README.md + source files; `.project_id` links a repo to a project
  reviews.jsonl           client reviews {project_id, text, rating, date, ...}
  proposals.jsonl         past proposals {text, outcome, cited_project_ids, ...}
GitHub repos can also be ingested through the GitHub MCP server (rag/ingest/github_ingest.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".dax", ".r", ".R", ".yml", ".yaml", ".css", ".ipynb"}


@dataclass
class Doc:
    id: str
    type: str  # cv | case_study | readme | code | review | proposal
    text: str
    meta: dict = field(default_factory=dict)


def _projects(root: Path) -> dict[str, dict]:
    p = root / "projects.json"
    if not p.exists():
        return {}
    return {d["id"]: d for d in json.loads(p.read_text(encoding="utf-8"))}


def _base_meta(persona: str, ptype: str, proj: dict | None) -> dict:
    proj = proj or {}
    return {"persona": persona, "type": ptype, "project_id": proj.get("id"), "project": proj.get("title"),
            "date": proj.get("date"), "client_industry": proj.get("industry"), "client": proj.get("client"),
            "outcome": None}


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)


def load_dir(root: Path, persona: str | None = None) -> list[Doc]:
    root = Path(root)
    persona = persona or root.name
    projects = _projects(root)
    by_title = {p["title"].lower(): p for p in projects.values()}
    docs: list[Doc] = []

    # CV: split into one item per project bullet where possible
    for cv in [root / "cv.pdf", root / "cv.md"]:
        if not cv.exists():
            continue
        text = _read_pdf(cv) if cv.suffix == ".pdf" else cv.read_text(encoding="utf-8")
        flat = re.sub(r"\s+", " ", text)
        hits = []
        for title, proj in by_title.items():
            i = flat.lower().find(title)
            if i >= 0:
                hits.append((i, proj))
        hits.sort()
        if hits:
            head = flat[:hits[0][0]].strip()
            if head:
                docs.append(Doc(f"{persona}:cv:header", "cv", head, _base_meta(persona, "cv", None)))
            for n, (i, proj) in enumerate(hits):
                end = hits[n + 1][0] if n + 1 < len(hits) else len(flat)
                docs.append(Doc(f"{persona}:cv:{proj['id']}", "cv", flat[i:end].strip(), _base_meta(persona, "cv", proj)))
        else:
            docs.append(Doc(f"{persona}:cv", "cv", flat, _base_meta(persona, "cv", None)))

    for md in sorted((root / "case_studies").glob("*.md")):
        proj = projects.get(md.stem) or {"id": md.stem, "title": md.stem}
        docs.append(Doc(f"{persona}:case:{md.stem}", "case_study", md.read_text(encoding="utf-8"),
                        _base_meta(persona, "case_study", proj)))

    for repo in sorted(p for p in (root / "repos").glob("*") if p.is_dir()):
        pid_file = repo / ".project_id"
        pid = pid_file.read_text(encoding="utf-8").strip() if pid_file.exists() else repo.name
        proj = projects.get(pid) or {"id": pid, "title": repo.name}
        readme = repo / "README.md"
        if readme.exists():
            docs.append(Doc(f"{persona}:readme:{repo.name}", "readme", readme.read_text(encoding="utf-8"),
                            {**_base_meta(persona, "readme", proj), "repo": repo.name}))
        for f in sorted(repo.rglob("*")):
            if f.is_file() and (f.suffix in CODE_EXT or f.name == "Dockerfile") and f.name != "README.md":
                rel = f.relative_to(repo).as_posix()
                docs.append(Doc(f"{persona}:code:{repo.name}/{rel}", "code", f.read_text(encoding="utf-8", errors="ignore"),
                                {**_base_meta(persona, "code", proj), "repo": repo.name, "path": rel}))

    rv = root / "reviews.jsonl"
    if rv.exists():
        for line in rv.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                proj = projects.get(r.get("project_id")) or {"id": r.get("project_id")}
                m = _base_meta(persona, "review", proj)
                m["rating"] = r.get("rating")
                docs.append(Doc(f"{persona}:review:{r['id']}", "review", r["text"], m))

    pp = root / "proposals.jsonl"
    if pp.exists():
        for line in pp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                cited = r.get("cited_project_ids") or []
                proj = projects.get(cited[0]) if cited else None
                m = _base_meta(persona, "proposal", proj)
                m.update(outcome=r.get("outcome"), cited_project_ids=cited, date=r.get("date"),
                         job_title=r.get("job_title"), job_category=r.get("job_category"))
                docs.append(Doc(f"{persona}:proposal:{r['id']}", "proposal", r["text"], m))
    return docs
