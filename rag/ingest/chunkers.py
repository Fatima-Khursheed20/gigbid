"""Chunkers. V0 uses fixed-size character windows; every other variant uses structure-aware chunks
(markdown sections, whole small code files, one proposal/review/CV item per chunk)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..skills import extract_skills
from .loaders import Doc


@dataclass
class Chunk:
    id: str
    doc_id: str
    text: str
    meta: dict = field(default_factory=dict)


def fixed_chunks(docs: list[Doc], size: int = 400, overlap: int = 50) -> list[Chunk]:
    out = []
    for d in docs:
        t = d.text
        i = n = 0
        while i < len(t):
            piece = t[i:i + size]
            out.append(Chunk(f"{d.id}#f{n}", d.id, piece, {**d.meta, "skills": extract_skills(piece)}))
            i += size - overlap
            n += 1
    return out


def _split_md(text: str, max_chars: int) -> list[str]:
    parts = re.split(r"\n(?=#{1,3} )", text)
    out: list[str] = []
    title = parts[0].splitlines()[0] if parts and parts[0].startswith("#") else ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if title and not p.startswith(title):
            p = f"{title}\n{p}"  # keep the document title with every section
        while len(p) > max_chars:
            cut = p.rfind("\n", 0, max_chars)
            cut = cut if cut > max_chars // 3 else max_chars
            out.append(p[:cut])
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out


def structured_chunks(docs: list[Doc], max_chars: int = 700) -> list[Chunk]:
    out = []
    for d in docs:
        if d.type in ("case_study", "readme"):
            pieces = _split_md(d.text, max_chars)
        elif d.type == "code":
            header = f"File {d.meta.get('path')} in repo {d.meta.get('repo')}\n"
            pieces = [header + d.text[:max_chars * 2]]
        else:
            pieces = [d.text[i:i + max_chars * 2] for i in range(0, max(1, len(d.text)), max_chars * 2)]
        for n, p in enumerate(pieces):
            out.append(Chunk(f"{d.id}#s{n}", d.id, p, {**d.meta, "skills": extract_skills(p)}))
    return out
