"""Render persona catalogs into a realistic, messy portfolio corpus (SYNTHETIC).

Each project is described three different ways (case study prose, repo README, CV bullet) plus code,
a client review and past proposals that cite it. Skills in `implied` are never named in prose — they
only show up in source code or as descriptive phrases — so naive retrieval has to work for them.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .personas import PERSONAS, all_projects
from .taxonomy import SKILLS

def _case_study(p: dict, rng: random.Random) -> str:
    implied_desc = [SKILLS[s]["desc"] for s in p["implied"]]
    lines = [
        f"# {p['title']}",
        "",
        f"*Client:* {p['client']} · *Industry:* {p['industry']} · *Delivered:* {p['date']}",
        "",
        "## The problem",
        p["problem"],
        "",
        "## What I built",
        p["approach"] + " " + (
            f"Under the hood this involved {', '.join(implied_desc)}." if implied_desc else ""),
        "",
        "## Results",
        p["result"],
        "",
        "## Stack",
        ", ".join(p["explicit"]) + rng.choice([" (plus the usual supporting tools).", ".", " and a few internal libraries."]),
    ]
    return "\n".join(lines) + "\n"


def _readme(p: dict, rng: random.Random) -> str:
    if p["readme_style"] == "clear":
        intro = f"{p['approach']} Built with {', '.join(p['explicit'][:3])}."
        feats = [SKILLS[s]["desc"].capitalize() for s in p["skills"][:4]]
    else:
        # Deliberately vague README: says what it is for, not what it uses.
        intro = rng.choice([
            "Internal tooling written for a client engagement. See `src/` for details.",
            "Service extracted from a production project; documentation is minimal.",
            "Prototype that later went to production. Ask me for a walkthrough.",
        ])
        feats = [rng.choice(["Configurable via environment variables", "Runs locally with one command",
                             "Has a small test suite", "Deployed behind the client's VPN"])]
    lines = [f"# {p['repo']}", "", intro, "", "## Features"] + [f"- {f}" for f in feats] + [
        "", "## Running", "```bash", "make dev", "```", "", f"_Context: {p['industry']} project, {p['date']}._"]
    return "\n".join(lines) + "\n"


def _file_for(code: str) -> str:
    c = code.lstrip()
    if c.startswith("FROM "):
        return "Dockerfile"
    if c.startswith("on: "):
        return ".github/workflows/ci.yml"
    if c.startswith("@tailwind"):
        return "src/styles.css"
    if c.startswith(("CREATE TABLE", "WITH ", "{{")):
        return "models/core.sql"
    if c.startswith("-- DAX"):
        return "reports/measures.dax"
    if c.startswith("library("):
        return "analysis/report.R"
    if c.startswith("# looker") or c.startswith("# metabase"):
        return "bi/config.yaml"
    if c.startswith(("export", "import {")) or (c.startswith("import ") and " from '" in c):
        return "src/index.ts"
    return "src/main.py"


def _code_files(p: dict) -> dict[str, str]:
    """Spread each skill's tell-tale line into the file where it would really live."""
    files: dict[str, list[str]] = {}
    for s in p["skills"]:
        code = SKILLS[s]["code"]
        files.setdefault(_file_for(code), []).append(code)
    out = {}
    for name, lines in files.items():
        if name.endswith(".py"):
            body = [f"# {p['repo']} — core module", *lines, "", "", "def main() -> None:",
                    '    """Entry point; wiring omitted for brevity."""', "", "", "if __name__ == '__main__':", "    main()"]
        elif name.endswith(".ts"):
            body = [f"// {p['repo']} — core module", *lines, "",
                    "export async function main(): Promise<void> {", "  // wiring omitted for brevity", "}"]
        else:
            body = lines
        out[name] = "\n".join(body) + "\n"
    return out


REVIEW_OPENERS = ["Great to work with.", "Would hire again.", "Exceeded expectations.", "Solid work.",
                  "Communication was excellent."]


def _review(p: dict, rng: random.Random) -> dict:
    rating = rng.choices([5.0, 4.8, 4.5, 4.0], weights=[6, 3, 2, 1])[0]
    text = (f"{rng.choice(REVIEW_OPENERS)} {p['result'].split(';')[0]}. "
            f"{rng.choice(['Delivered on time.', 'Asked smart questions up front.', 'Clear documentation at handover.', 'Fixed issues quickly after launch.'])}")
    return {"id": f"rev-{p['id']}", "project_id": p["id"], "client": p["client"], "industry": p["industry"],
            "date": p["date"], "rating": rating, "text": text}


def _cv_pdf(persona: str, path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    meta = PERSONAS[persona]
    styles = getSampleStyleSheet()
    story = [Paragraph(meta["name"], styles["Title"]), Paragraph(meta["headline"], styles["Heading3"]),
             Paragraph(f"{meta['location']} · {meta['years']} years experience · SYNTHETIC PERSONA FOR COURSEWORK",
                       styles["Normal"]), Spacer(1, 10), Paragraph("Selected work", styles["Heading2"])]
    for p in all_projects(persona):
        story.append(Paragraph(
            f"<b>{p['title']}</b> — {p['client']}, {p['date']}. {p['result']} "
            f"<i>Tools: {', '.join(p['explicit'])}.</i>", styles["Normal"]))
        story.append(Spacer(1, 4))
    SimpleDocTemplate(str(path), pagesize=A4, title=f"CV {meta['name']}").build(story)


def render_persona(persona: str, out_root: Path, seed: int = 7) -> None:
    rng = random.Random(f"{seed}-{persona}")
    root = out_root / persona
    (root / "case_studies").mkdir(parents=True, exist_ok=True)
    (root / "repos").mkdir(parents=True, exist_ok=True)
    meta = PERSONAS[persona]
    projects = all_projects(persona)
    profile = {k: v for k, v in meta.items() if k != "projects"}
    profile["persona"] = persona
    profile["skills"] = sorted({s for p in projects for s in p["explicit"]})  # declared skills (explicit only)
    profile["synthetic"] = True
    (root / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    (root / "projects.json").write_text(json.dumps(projects, indent=2), encoding="utf-8")
    reviews = []
    for p in projects:
        (root / "case_studies" / f"{p['id']}.md").write_text(_case_study(p, rng), encoding="utf-8")
        repo = root / "repos" / p["repo"]
        (repo / "src").mkdir(parents=True, exist_ok=True)
        (repo / "README.md").write_text(_readme(p, rng), encoding="utf-8")
        for name, code in _code_files(p).items():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(code, encoding="utf-8")
        (repo / ".project_id").write_text(p["id"], encoding="utf-8")
        reviews.append(_review(p, rng))
    with (root / "reviews.jsonl").open("w", encoding="utf-8") as f:
        for r in reviews:
            f.write(json.dumps(r) + "\n")
    _cv_pdf(persona, root / "cv.pdf")
