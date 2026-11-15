"""Minimal Markdown -> PDF (ReportLab) for the R&D report: headings, paragraphs, bullet/numbered lists,
pipe tables, inline **bold**/*italic*/`code`, page numbers.

    python -m scripts.md_to_pdf docs/report/REPORT.md docs/report/GigBid_RnD_Report.pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.2, leading=12, alignment=TA_LEFT, spaceAfter=4)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.4, leading=9.2)
H = {1: ParagraphStyle("h1", parent=ss["Title"], fontSize=16, spaceAfter=6),
     2: ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=8, spaceAfter=4),
     3: ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=3)}


def inline(t: str) -> str:
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"`([^`]+)`", r"<font face='Courier' size='8'>\1</font>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<link href='\2' color='blue'>\1</link>", t)
    return t


def table(lines: list[str]):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines if not re.match(r"^\s*\|?\s*:?-{2,}", ln)]
    data = [[Paragraph(inline(c), SMALL) for c in r] for r in rows]
    t = Table(data, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#94a3b8")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    return t


def convert(src: Path, dst: Path) -> int:
    story = []
    lines = src.read_text(encoding="utf-8").splitlines()
    i = 0
    para: list[str] = []

    def flush():
        if para:
            story.append(Paragraph(inline(" ".join(para)), BODY))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "\\pagebreak":
            flush()
            story.append(PageBreak())
        elif m := re.match(r"^(#{1,3})\s+(.*)", ln):
            flush()
            story.append(Paragraph(inline(m.group(2)), H[len(m.group(1))]))
        elif ln.strip().startswith("|"):
            flush()
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            story.append(table(block))
            story.append(Spacer(1, 4))
            continue
        elif re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            flush()
            items, numbered = [], bool(re.match(r"^\s*\d+\.", ln))
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                txt = re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                    txt += " " + lines[i].strip()
                    i += 1
                items.append(ListItem(Paragraph(inline(txt), BODY), leftIndent=10))
            story.append(ListFlowable(items, bulletType="1" if numbered else "bullet", leftIndent=12, bulletFontSize=7))
            continue
        elif not ln.strip():
            flush()
        else:
            para.append(ln.strip())
        i += 1
    flush()

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(A4[0] - 1.5 * cm, 1 * cm, f"GigBid R&D report · page {doc.page}")

    doc = SimpleDocTemplate(str(dst), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.4 * cm,
                            bottomMargin=1.5 * cm, title="GigBid R&D report")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    from pypdf import PdfReader

    return len(PdfReader(str(dst)).pages)


if __name__ == "__main__":
    n = convert(Path(sys.argv[1]), Path(sys.argv[2]))
    print("pages:", n)
