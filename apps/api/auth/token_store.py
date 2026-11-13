"""Encrypted per-user OAuth/API token store (E4). Tokens are Fernet-encrypted at rest and never logged."""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet

from common.settings import get_settings

from .. import db


def _fernet() -> Fernet:
    s = get_settings()
    key = s.token_encryption_key or base64.urlsafe_b64encode(hashlib.sha256(
        ("gigbid-token-store|" + s.app_secret_key).encode()).digest()).decode()
    return Fernet(key)


async def put(user_id: str, provider: str, payload: dict) -> None:
    ct = _fernet().encrypt(json.dumps(payload).encode()).decode()
    await db.execute("insert into oauth_tokens(user_id,provider,ciphertext) values (%s,%s,%s) on conflict (user_id,provider) "
                     "do update set ciphertext=excluded.ciphertext, updated_at=now()", user_id, provider, ct)


async def get(user_id: str, provider: str) -> dict | None:
    row = await db.fetchone("select ciphertext from oauth_tokens where user_id=%s and provider=%s", user_id, provider)
    if not row:
        return None
    return json.loads(_fernet().decrypt(row["ciphertext"].encode()))


async def delete(user_id: str, provider: str) -> None:
    await db.execute("delete from oauth_tokens where user_id=%s and provider=%s", user_id, provider)


async def connected(user_id: str) -> list[str]:
    return [r["provider"] for r in await db.fetch("select provider from oauth_tokens where user_id=%s", user_id)]
