"""Run the single-process app and report peak RSS while the worker analyses jobs (deployment sizing)."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time

import psutil

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
os.environ["PORT"] = "10001"
peak = 0


def watch():
    global peak
    p = psutil.Process()
    while True:
        peak = max(peak, p.memory_info().rss)
        time.sleep(0.2)


def drive():
    import httpx

    time.sleep(25)
    c = httpx.Client(base_url="http://127.0.0.1:10001", timeout=120)
    from common.settings import get_settings

    s = get_settings()
    for _ in range(60):
        try:
            c.get("/api/health")
            break
        except Exception:  # noqa: BLE001
            time.sleep(5)
    tok = c.post("/api/auth/login", json={"email": s.reviewer_email, "password": s.reviewer_password}).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    for j in ["job-dev-ai-012", "job-dev-ai-015", "job-dev-ai-020"]:
        c.post(f"/api/jobs/{j}/analyze")
    for _ in range(int(os.environ.get("PROBE_SECONDS", "240")) // 10):
        time.sleep(10)
        print(f"peak RSS {peak / 1e6:.0f} MB", flush=True)
    os._exit(0)


if __name__ == "__main__":
    threading.Thread(target=watch, daemon=True).start()
    threading.Thread(target=drive, daemon=True).start()
    import uvicorn

    import scripts.allinone as a

    uvicorn.run(a.build_app(), host="127.0.0.1", port=10001, loop="none", log_level="warning")
