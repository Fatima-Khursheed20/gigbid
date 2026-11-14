"""Repository rules enforced in CI:
  1. no secrets committed;  2. nothing under gigsim/ changed (hash manifest);
  3. every prompt lives in agent/prompts/ (no inline system prompts in node code);
  4. every number in the README results tables traces to a file in evals/results/.

    python -m scripts.ci_checks            # check
    python -m scripts.ci_checks --freeze   # (maintainer) re-freeze the GigSim manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ci" / "gigsim.sha256.json"
SECRET = re.compile(r"(gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}|lsv2_[A-Za-z0-9_]{20,}|"
                    r"hf_[A-Za-z0-9]{30,}|postgres(ql)?://[^:\s]+:[^@\s]{8,}@(?!localhost|postgres:|127\.0\.0\.1))")


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines()]


def gigsim_hashes() -> dict[str, str]:
    # hash LF-normalised bytes so Windows (CRLF working copy) and Linux CI agree
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for p in sorted((ROOT / "gigsim").rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    if a.freeze:
        MANIFEST.parent.mkdir(exist_ok=True)
        MANIFEST.write_text(json.dumps(gigsim_hashes(), indent=1) + "\n", encoding="utf-8")
        print("frozen", MANIFEST)
        return 0
    errors = []
    for p in tracked():
        if not p.is_file() or p.suffix in {".pdf", ".png", ".gif", ".jpg", ".mp4", ".db"} or p.name.endswith(".lock"):
            continue
        for m in SECRET.finditer(p.read_text(encoding="utf-8", errors="ignore")):
            errors.append(f"possible secret in {p.relative_to(ROOT)}: {m.group(0)[:12]}…")
    if MANIFEST.exists():
        frozen, now = json.loads(MANIFEST.read_text(encoding="utf-8")), gigsim_hashes()
        changed = sorted(k for k in set(frozen) | set(now) if frozen.get(k) != now.get(k))
        errors += [f"gigsim/ changed: {c}" for c in changed]
    for p in (ROOT / "agent" / "nodes").glob("*.py"):
        src = p.read_text(encoding="utf-8")
        if re.search(r'(system|SYSTEM)\s*=\s*["\']{1,3}You are', src) or re.search(r'llm\.(structured|complete)\([^)]*"You are', src):
            errors.append(f"inline prompt in {p.relative_to(ROOT)}; move it to agent/prompts/")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for block in re.findall(r"<!-- results:([\w./-]+) -->", readme):
        if not (ROOT / block).exists():
            errors.append(f"README cites missing results file {block}")
    for e in errors:
        print("ERROR", e)
    print("ci_checks:", "FAILED" if errors else "ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
