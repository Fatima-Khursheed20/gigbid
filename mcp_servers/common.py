"""Shared helpers for GigBid's MCP servers: request headers, bearer auth middleware, trace propagation."""

from __future__ import annotations

import contextvars
import os
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from common.tracing import TRACE_HEADER, set_trace_id

# In-process transports (tests, offline evals) have no HTTP headers; the in-process ToolBus sets the same
# values here before it opens its sessions, and server tasks inherit them.
REQUEST_DEFAULTS: contextvars.ContextVar[dict] = contextvars.ContextVar("mcp_request_defaults", default=None)


def header(ctx: Any, name: str, default: str | None = None) -> str | None:
    """Read an HTTP header from the MCP request context, else the in-process defaults, else `default`."""
    try:
        req = ctx.request_context.request
        if req is not None:
            v = req.headers.get(name)
            if v:
                return v
    except Exception:  # noqa: BLE001
        pass
    return (REQUEST_DEFAULTS.get() or {}).get(name, default)


def trace_from(ctx: Any) -> str:
    return set_trace_id(header(ctx, TRACE_HEADER))


class BearerAuth(BaseHTTPMiddleware):
    """Bearer-token auth on the HTTP endpoint (A2). Health checks stay open."""

    def __init__(self, app, token_env: str, default: str | None = None) -> None:
        super().__init__(app)
        self.token = os.environ.get(token_env, default or "")

    async def dispatch(self, request, call_next):
        if request.url.path.endswith(("/health", "/healthz")):
            return await call_next(request)
        if self.token:
            got = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if got != self.token:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def http_app(mcp, token_env: str | None = None, default_token: str | None = None):
    """Streamable-HTTP ASGI app for a FastMCP server, with optional bearer auth and a /health route."""
    from starlette.responses import PlainTextResponse

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(_request):  # noqa: ANN202
        return PlainTextResponse("ok")

    app = mcp.streamable_http_app()
    if token_env:
        app.add_middleware(BearerAuth, token_env=token_env, default=default_token)
    return app


def transport_security():
    """DNS-rebinding protection: on by default for localhost-only use; containers pass their service hostnames
    in MCP_ALLOWED_HOSTS (comma separated) or disable it behind bearer auth with MCP_ALLOWED_HOSTS=*."""
    from mcp.server.transport_security import TransportSecuritySettings

    hosts = os.environ.get("MCP_ALLOWED_HOSTS", "*")
    if hosts.strip() == "*":
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    allowed = [h.strip() for h in hosts.split(",") if h.strip()]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=allowed,
                                     allowed_origins=[f"http://{h}" for h in allowed])
