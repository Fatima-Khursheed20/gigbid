"""End-to-end smoke test through the public HTTP API (local stack or the deployed URL).

    python -m scripts.e2e_api --base http://localhost:8000 --email reviewer@... --password ... [--job job-dev-ai-001]
Logs in, analyses a job via the worker, waits on the run, reads the proposal studio, approves, and checks the
pipeline. Prints a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import time

import httpx


def wait_run(c: httpx.Client, run_id: str, timeout: float = 300) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/api/runs/{run_id}").json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(2)
    raise TimeoutError(run_id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--job", default="job-dev-ai-001")
    ap.add_argument("--approve", action="store_true")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.base, timeout=60)
    tok = c.post("/api/auth/login", json={"email": a.email, "password": a.password}).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    out: dict = {"health": c.get("/api/health").json()}
    run = c.post(f"/api/jobs/{a.job}/analyze").json()
    r = wait_run(c, run["run_id"])
    out["analysis_run"] = {k: r[k] for k in ("status", "latency_s", "tokens", "usd")}
    out["nodes"] = [e["node"] for e in r["events"] if e["kind"] == "node_end"]
    detail = c.get(f"/api/jobs/{a.job}").json()
    out["decision"] = detail.get("decision")
    studio = c.get(f"/api/proposals/{a.job}").json()
    out["pending_approval"] = studio["pending"]
    if studio["pending"]:
        p = studio["payload"]
        out["preview"] = p["preview"]
        out["draft_words"] = p["draft"]["word_count"]
        out["verification"] = p.get("verification")
        if a.approve:
            run2 = c.post(f"/api/proposals/{a.job}/decision", json={"action": "approve"}).json()
            r2 = wait_run(c, run2["run_id"])
            out["submit_run"] = {k: r2[k] for k in ("status", "latency_s")}
            out["pipeline"] = c.get("/api/pipeline").json()[:3]
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
