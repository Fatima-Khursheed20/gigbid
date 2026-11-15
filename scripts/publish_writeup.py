"""Render docs/WRITEUP.md to a standalone blog page (published on the repo's GitHub Pages, gh-pages branch).

    python -m scripts.publish_writeup OUT_DIR     # needs the `markdown` package
"""

from __future__ import annotations

import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/Fatima-Khursheed20/gigbid"

CSS = """
:root{--bg:#fdfcfa;--fg:#1d1d1f;--muted:#5f6368;--accent:#0b6e4f;--rule:#e4e1da;--code:#f3f1ec}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#ececec;--muted:#a0a0a0;--accent:#5fd3a8;--rule:#2c2c2c;--code:#1f1f1f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.7 Georgia,'Iowan Old Style',serif}
main{max-width:720px;margin:0 auto;padding:48px 16px 80px}
h1{font:700 2.1rem/1.2 system-ui,sans-serif;margin:0 0 .6em}h2{font:650 1.35rem/1.3 system-ui,sans-serif;margin:2em 0 .5em}
h3{font:600 1.1rem system-ui,sans-serif}a{color:var(--accent)}hr{border:0;border-top:1px solid var(--rule);margin:2.5em 0}
code{background:var(--code);padding:.1em .35em;border-radius:4px;font-size:.88em}pre{background:var(--code);padding:14px;overflow-x:auto;border-radius:6px}
pre code{padding:0}table{border-collapse:collapse;width:100%;font:15px/1.4 system-ui,sans-serif;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--rule);padding:6px 8px;text-align:left}blockquote{margin:0;padding-left:16px;border-left:3px solid var(--rule);color:var(--muted)}
.meta{font:14px system-ui,sans-serif;color:var(--muted);margin-bottom:2em}
"""


def main(out_dir: str) -> None:
    src = (ROOT / "docs" / "WRITEUP.md").read_text(encoding="utf-8")
    # repo-relative links resolve to GitHub, not to the Pages site
    src = src.replace("](docs/", f"]({REPO}/blob/main/docs/").replace("](evals/", f"]({REPO}/blob/main/evals/")
    body = markdown.markdown(src, extensions=["tables", "fenced_code"])
    title = src.splitlines()[0].lstrip("# ").strip()
    words = len(src.split())
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<meta name="description" content="Technical write-up from building GigBid, a multi-agent freelancer copilot.">
<style>{CSS}</style></head><body><main>
<p class="meta">AI-4016 Agentic AI, FAST-NUCES · {words:,} words ·
<a href="{REPO}">source code</a> · <a href="https://gigbid-p090.onrender.com">live app</a></p>
{body}
</main></body></html>"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print("wrote", out / "index.html", words, "words")


if __name__ == "__main__":
    main(sys.argv[1])
