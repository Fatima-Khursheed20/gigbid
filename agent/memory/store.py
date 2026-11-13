"""Long-term memory on a LangGraph store (C2, R7). Two promoted stores per user:

  ("style", user_id)    learned writing rules from the user's edits, e.g. "Never use the word 'passionate'"
  ("outcome", user_id)  what won / got replies per job category

Raw observations go to *staging* namespaces ("style_obs", ...) and ("outcome_obs", ...). Only
promotion_rules.py moves knowledge from staging into the promoted namespaces, and nothing writes raw tool
output to memory. Users can view and delete promoted items from Settings → Memory.
"""

from __future__ import annotations

import time
import uuid
from typing import Any


def ns(kind: str, user_id: str) -> tuple[str, str]:
    return (kind, user_id)


async def style_rules(store: Any, user_id: str) -> list[str]:
    if store is None:
        return []
    items = await store.asearch(ns("style", user_id), limit=50)
    return [i.value["rule"] for i in items if i.value.get("rule")]


async def outcome_hints(store: Any, user_id: str, category: str) -> list[str]:
    if store is None:
        return []
    item = await store.aget(ns("outcome", user_id), category)
    if not item:
        return []
    v = item.value
    return [f"In {category} jobs you've had {v['replied']}/{v['submitted']} replies; "
            f"proposals citing {', '.join(v.get('top_projects', [])[:2]) or 'specific projects'} did best."]


async def observe(store: Any, kind: str, user_id: str, value: dict) -> str:
    key = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    await store.aput(ns(f"{kind}_obs", user_id), key, {**value, "ts": time.time()})
    return key


async def list_memory(store: Any, user_id: str) -> dict[str, list[dict]]:
    out = {}
    for kind in ("style", "outcome"):
        items = await store.asearch(ns(kind, user_id), limit=100)
        out[kind] = [{"key": i.key, **i.value} for i in items]
    return out


async def delete_memory(store: Any, user_id: str, kind: str, key: str) -> None:
    await store.adelete(ns(kind, user_id), key)
    # a deleted rule must not be re-promoted from the same old observations
    await store.aput(ns(f"{kind}_tombstone", user_id), key, {"deleted_at": time.time()})
