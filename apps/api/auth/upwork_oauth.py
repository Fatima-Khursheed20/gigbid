"""OAuth 2.1 (authorization code + PKCE, dynamic client registration) for the official Upwork MCP server, using
the MCP Python SDK's OAuthClientProvider. Tokens are persisted through the encrypted token store, per user.

Flow: /api/auth/upwork/start launches the SDK flow in a background task; the SDK calls `redirect_handler`
with the authorization URL (returned to the browser), then awaits `callback_handler`, which is resolved by
/api/auth/upwork/callback when Upwork redirects back with ?code&state.
"""

from __future__ import annotations

import asyncio

from common.settings import get_settings

from . import token_store

_pending: dict[str, asyncio.Future] = {}
_auth_urls: dict[str, asyncio.Future] = {}


class _Storage:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        d = await token_store.get(self.user_id, "upwork")
        return OAuthToken.model_validate(d["tokens"]) if d and d.get("tokens") else None

    async def set_tokens(self, tokens) -> None:
        d = await token_store.get(self.user_id, "upwork") or {}
        d["tokens"] = tokens.model_dump(mode="json")
        await token_store.put(self.user_id, "upwork", d)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        d = await token_store.get(self.user_id, "upwork")
        return OAuthClientInformationFull.model_validate(d["client"]) if d and d.get("client") else None

    async def set_client_info(self, info) -> None:
        d = await token_store.get(self.user_id, "upwork") or {}
        d["client"] = info.model_dump(mode="json")
        await token_store.put(self.user_id, "upwork", d)


def provider_for(user_id: str):
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    s = get_settings()
    loop = asyncio.get_event_loop()

    async def redirect_handler(url: str) -> None:
        _auth_urls.setdefault(user_id, loop.create_future()).set_result(url)

    async def callback_handler() -> tuple[str, str | None]:
        fut = _pending.setdefault(user_id, loop.create_future())
        return await asyncio.wait_for(fut, timeout=600)

    return OAuthClientProvider(
        server_url=s.upwork_mcp_url,
        client_metadata=OAuthClientMetadata(client_name="GigBid", redirect_uris=[s.upwork_oauth_redirect_url],
                                            grant_types=["authorization_code", "refresh_token"],
                                            response_types=["code"], token_endpoint_auth_method="none"),
        storage=_Storage(user_id), redirect_handler=redirect_handler, callback_handler=callback_handler)


async def start(user_id: str) -> str:
    """Begin the flow; returns the authorization URL the browser must open."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    loop = asyncio.get_event_loop()
    _auth_urls[user_id] = loop.create_future()
    _pending[user_id] = loop.create_future()
    client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": get_settings().upwork_mcp_url,
                                              "auth": provider_for(user_id)}})

    async def _run() -> None:
        try:
            await client.get_tools(server_name="upwork")  # triggers 401 -> discovery -> DCR -> redirect -> callback
        except Exception:  # noqa: BLE001 - surfaced to the user as "not connected"
            pass

    asyncio.create_task(_run())
    return await asyncio.wait_for(_auth_urls[user_id], timeout=30)


def finish(user_id: str, code: str, state: str | None) -> None:
    fut = _pending.get(user_id)
    if fut and not fut.done():
        fut.set_result((code, state))
