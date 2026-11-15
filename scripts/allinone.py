"""Single-process deployment for small free hosts (Render free: 512 MB RAM).

The same code as `docker compose`, but GigSim, the three MCP servers (streamable HTTP, mounted under /mcp/*),
the API (serving the web build) and the Arq worker all share one Python process and one event loop:

    GIGSIM_BASE_URL     = http://127.0.0.1:$PORT/gigsim
    MCP_PORTFOLIO_URL   = http://127.0.0.1:$PORT/mcp/portfolio/mcp   (etc.)

Agents still reach every capability through MCP over HTTP and the worker still consumes the Redis queue; only
process boundaries are removed. ONNX Runtime runs single-threaded without its memory arena to stay < 512 MB.

    python -m scripts.allinone
"""

from __future__ import annotations

import asyncio
import contextlib
import os

PORT = int(os.environ.get("PORT", "10000"))
BASE = f"http://127.0.0.1:{PORT}"
os.environ.setdefault("GIGSIM_BASE_URL", f"{BASE}/gigsim")
os.environ.setdefault("MCP_PORTFOLIO_URL", f"{BASE}/mcp/portfolio/mcp")
os.environ.setdefault("MCP_MARKETPLACE_URL", f"{BASE}/mcp/marketplace/mcp")
os.environ.setdefault("MCP_WORKSPACE_URL", f"{BASE}/mcp/workspace/mcp")
os.environ.setdefault("MCP_ALLOWED_HOSTS", "*")
os.environ.setdefault("LLM_CONCURRENCY", "2")


def _lean_onnx() -> None:
    import onnxruntime as ort

    orig = ort.InferenceSession.__init__

    def patched(self, path_or_bytes, sess_options=None, *a, **k):
        so = sess_options or ort.SessionOptions()
        so.enable_cpu_mem_arena = False
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        return orig(self, path_or_bytes, so, *a, **k)

    ort.InferenceSession.__init__ = patched


def build_app():
    _lean_onnx()
    from starlette.applications import Starlette
    from starlette.routing import Mount

    import gigsim.app as gs
    from apps.api.main import app as api
    from apps.api.main import lifespan as api_lifespan
    from mcp_servers.common import http_app
    from mcp_servers.marketplace.server import mcp as mk
    from mcp_servers.portfolio.server import mcp as pf
    from mcp_servers.workspace.server import mcp as ws

    os.environ.setdefault("MCP_MARKETPLACE_TOKEN", os.environ.get("MCP_MARKETPLACE_TOKEN", "change-me"))
    subapps = {"portfolio": http_app(pf, "PORTFOLIO_MCP_TOKEN"), "marketplace": http_app(mk, "MCP_MARKETPLACE_TOKEN"),
               "workspace": http_app(ws, "WORKSPACE_MCP_TOKEN")}

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with gs.lifespan(gs.app), pf.session_manager.run(), mk.session_manager.run(), ws.session_manager.run(), \
                api_lifespan(api):
            worker_task = None
            if os.environ.get("REDIS_URL"):
                from arq.worker import Worker

                from worker.main import WorkerSettings as WS

                w = Worker(functions=WS.functions, cron_jobs=WS.cron_jobs, redis_settings=WS.redis_settings,
                           max_jobs=1, job_timeout=WS.job_timeout, keep_result=WS.keep_result, handle_signals=False)
                worker_task = asyncio.create_task(w.async_run())
            try:
                yield
            finally:
                if worker_task:
                    worker_task.cancel()

    return Starlette(routes=[Mount("/gigsim", app=gs.app),
                             Mount("/mcp/portfolio", app=subapps["portfolio"]),
                             Mount("/mcp/marketplace", app=subapps["marketplace"]),
                             Mount("/mcp/workspace", app=subapps["workspace"]),
                             Mount("/", app=api)], lifespan=lifespan)


def main() -> None:
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*", log_level="info")


if __name__ == "__main__":
    main()
