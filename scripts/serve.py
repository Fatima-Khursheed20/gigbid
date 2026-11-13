"""Start an ASGI app or the Arq worker with a psycopg-compatible event loop (Selector loop on Windows).

    python -m scripts.serve api|gigsim|portfolio|marketplace|workspace [--port N] [--host H]
    python -m scripts.serve worker
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

APPS = {
    "api": ("apps.api.main:app", False, 8000),
    "gigsim": ("gigsim.app:app", False, 8081),
    "portfolio": ("mcp_servers.portfolio.server:create_app", True, 8101),
    "marketplace": ("mcp_servers.marketplace.server:create_app", True, 8102),
    "workspace": ("mcp_servers.workspace.server:create_app", True, 8103),
}


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    ap = argparse.ArgumentParser()
    ap.add_argument("service", choices=[*APPS, "worker"])
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    a = ap.parse_args()
    if a.service == "worker":
        from arq.worker import run_worker

        from worker.main import WorkerSettings

        run_worker(WorkerSettings)
        return
    import uvicorn

    target, factory, port = APPS[a.service]
    host = a.host or ("0.0.0.0" if a.service == "api" else os.environ.get("INTERNAL_HOST", "127.0.0.1"))
    uvicorn.run(target, factory=factory, host=host, port=a.port or int(os.environ.get("PORT", port) if a.service == "api" else port),
                loop="none" if sys.platform == "win32" else "auto", log_level="info" if a.service == "api" else "warning",
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
