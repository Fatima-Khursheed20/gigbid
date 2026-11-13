"""LLM access for every node: model routing by node (from config), fallback model, JSON/Pydantic
outputs, disk cache, rate-limit handling, and a per-run token/cost/latency ledger (R8, E3, E5).

All providers in the open profile speak the OpenAI-compatible chat API (Groq, OpenRouter, Ollama).
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import cfg, model_for, price_for, profile
from .pii import mask
from .settings import ROOT, get_settings

log = logging.getLogger("gigbid.llm")
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """No provider configured / offline mode / provider down after retries and fallback."""


@dataclass
class Call:
    node: str
    model: str
    input_tokens: int
    output_tokens: int
    usd: float
    latency_s: float
    cached: bool
    ok: bool = True


@dataclass
class Ledger:
    calls: list[Call] = field(default_factory=list)

    def add(self, c: Call) -> None:
        self.calls.append(c)

    @property
    def tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.calls)

    @property
    def usd(self) -> float:
        return round(sum(c.usd for c in self.calls), 6)

    def by_node(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for c in self.calls:
            d = out.setdefault(c.node, {"calls": 0, "tokens": 0, "usd": 0.0, "latency_s": 0.0})
            d["calls"] += 1
            d["tokens"] += c.input_tokens + c.output_tokens
            d["usd"] = round(d["usd"] + c.usd, 6)
            d["latency_s"] = round(d["latency_s"] + c.latency_s, 3)
        return out

    def to_list(self) -> list[dict]:
        return [asdict(c) for c in self.calls]


_ledger: contextvars.ContextVar[Ledger | None] = contextvars.ContextVar("ledger", default=None)


def start_ledger() -> Ledger:
    led = Ledger()
    _ledger.set(led)
    return led


def current_ledger() -> Ledger | None:
    return _ledger.get()


# ----------------------------------------------------------------------------- cache
class _Cache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("create table if not exists c (k text primary key, v text)")
        self.lock = threading.Lock()

    def get(self, k: str) -> dict | None:
        with self.lock:
            r = self.db.execute("select v from c where k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else None

    def put(self, k: str, v: dict) -> None:
        with self.lock:
            self.db.execute("insert or replace into c values(?,?)", (k, json.dumps(v)))
            self.db.commit()


_CACHE: _Cache | None = None


def _cache() -> _Cache | None:
    global _CACHE
    if not cfg("models", "cache", default=True) or os.environ.get("LLM_CACHE", "1") == "0":
        return None
    if _CACHE is None:
        _CACHE = _Cache(Path(os.environ.get("LLM_CACHE_PATH", ROOT / ".cache" / "llm_cache.sqlite")))
    return _CACHE


# ----------------------------------------------------------------------------- provider
_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_CLIENT: httpx.AsyncClient | None = None


def _provider() -> tuple[str, str]:
    p = profile()
    s = get_settings()
    base = p.get("base_url") or os.environ.get(p.get("base_url_env", ""), "") or s.ollama_base_url
    key_env = p.get("api_key_env", "")
    key = os.environ.get(key_env, "") if key_env else "ollama"
    if not key and key_env == "GROQ_API_KEY":
        key = s.groq_api_key
    if not key and key_env == "OPENROUTER_API_KEY":
        key = s.openrouter_api_key
    return base.rstrip("/"), key


def available() -> bool:
    if get_settings().llm_offline or os.environ.get("LLM_OFFLINE") == "1":
        return False
    _, key = _provider()
    return bool(key)


def _client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(timeout=cfg("models", "timeout_s", default=60))
    return _CLIENT


async def _post(model: str, payload: dict) -> dict:
    base, key = _provider()
    sem = _SEMAPHORES.setdefault(model, asyncio.Semaphore(int(os.environ.get("LLM_CONCURRENCY", "2"))))
    last_err: Exception | None = None
    for attempt in range(6):
        async with sem:
            try:
                r = await _client().post(f"{base}/chat/completions", json=payload,
                                         headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as e:
                last_err = e
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
        if r.status_code == 429 or r.status_code >= 500:
            ra = r.headers.get("retry-after")
            wait = float(ra) if ra and ra.replace(".", "").isdigit() else 2.0 * (attempt + 1)
            last_err = RuntimeError(f"{r.status_code}: {r.text[:200]}")
            if r.status_code == 429 and "tokens per day" in r.text.lower():
                break  # daily quota exhausted: retrying is pointless, fall back instead
            await asyncio.sleep(min(wait, 30))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"LLM {model} HTTP {r.status_code}: {r.text[:300]}")
        return r.json()
    raise LLMUnavailable(f"{model}: {last_err}")


async def _complete(node: str, model: str, messages: list[dict], json_mode: bool, temperature: float,
                    max_tokens: int) -> tuple[str, dict, bool]:
    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature,
                               "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
        payload["include_reasoning"] = False
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    cache = _cache()
    if cache and (hit := cache.get(key)):
        return hit["text"], hit["usage"], True
    data = await _post(model, payload)
    text = data["choices"][0]["message"].get("content") or ""
    text = re.sub(r"(?s)<think>.*?</think>", "", text).strip()
    usage = data.get("usage") or {}
    if cache and text:
        cache.put(key, {"text": text, "usage": usage, "node": node})
    return text, usage, False


def _traced(fn):
    """Wrap with LangSmith @traceable when tracing is on, so each LLM call shows tokens per node."""
    try:
        from langsmith import traceable

        return traceable(run_type="llm", name="llm")(fn)
    except Exception:  # pragma: no cover
        return fn


@_traced
async def _call_model(node: str, model: str, messages: list[dict], json_mode: bool, temperature: float,
                      max_tokens: int) -> dict:
    t0 = time.perf_counter()
    text, usage, cached = await _complete(node, model, messages, json_mode, temperature, max_tokens)
    dt = time.perf_counter() - t0
    pin, pout = price_for(model)
    it, ot = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    usd = (it * pin + ot * pout) / 1e6
    if led := current_ledger():
        led.add(Call(node, model, it, ot, round(usd, 7), round(dt, 3), cached))
    return {"text": text, "model": model, "cached": cached,
            "usage_metadata": {"input_tokens": it, "output_tokens": ot, "total_tokens": it + ot},
            "ls_model_name": model, "ls_provider": profile().get("provider", "openai")}


async def complete(node: str, system: str, user: str, *, json_mode: bool = False, temperature: float | None = None,
                   max_tokens: int | None = None) -> str:
    """Plain completion with model routing + fallback. Raises LLMUnavailable when offline."""
    if not available():
        raise LLMUnavailable("LLM offline or no API key configured")
    model = model_for(node)
    temperature = cfg("models", "temperature", default=0.2) if temperature is None else temperature
    max_tokens = max_tokens or cfg("models", "max_output_tokens", default=1200)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        out = await _call_model(node, model, messages, json_mode, temperature, max_tokens)
        return out["text"]
    except (LLMUnavailable, RuntimeError) as e:
        fb = profile().get("fallback", {}).get(model)
        if not fb:
            raise LLMUnavailable(str(e)) from e
        log.warning("node %s: %s failed (%s); falling back to %s", node, model, mask(str(e))[:120], fb)
        out = await _call_model(node, fb, messages, json_mode, temperature, max_tokens)
        return out["text"]


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start > 0:
        text = text[start:]
    end = max(text.rfind("}"), text.rfind("]"))
    if end >= 0:
        text = text[:end + 1]
    return json.loads(text)


async def structured(node: str, system: str, user: str, schema: type[T], *, temperature: float | None = None,
                     max_tokens: int | None = None) -> T:
    """JSON output validated into a Pydantic model; one repair attempt, then the fallback model."""
    sys = system + "\n\nRespond with a single JSON object only. JSON schema:\n" + json.dumps(
        schema.model_json_schema(), separators=(",", ":"))
    text = await complete(node, sys, user, json_mode=True, temperature=temperature, max_tokens=max_tokens)
    try:
        return schema.model_validate(_extract_json(text))
    except (ValidationError, json.JSONDecodeError, ValueError) as e:
        repair = (user + "\n\nYour previous answer was invalid: " + str(e)[:400] +
                  "\nReturn corrected JSON only.")
        text = await complete(node, sys, repair, json_mode=True, temperature=0.0, max_tokens=max_tokens)
        return schema.model_validate(_extract_json(text))


def chat_model(node: str):
    """LangChain chat model for tool-calling agents (single-agent / supervisor baselines)."""
    from langchain_openai import ChatOpenAI

    base, key = _provider()
    return ChatOpenAI(model=model_for(node), base_url=base, api_key=key or "none",
                      temperature=cfg("models", "temperature", default=0.2),
                      max_tokens=cfg("models", "max_output_tokens", default=1200), max_retries=4)
