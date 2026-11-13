"""Loads agent/config.yaml. Every node's model, every threshold and every rule comes from here."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .settings import ROOT, get_settings

CONFIG_PATH = Path(os.environ.get("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"))


@lru_cache
def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    s = get_settings()
    if s.marketplace_mode:
        cfg["marketplace"]["mode"] = s.marketplace_mode
    if s.model_profile:
        cfg["models"]["profile"] = s.model_profile
    return cfg


def cfg(*path: str, default: Any = None) -> Any:
    node: Any = load_config()
    for p in path:
        if not isinstance(node, dict) or p not in node:
            return default
        node = node[p]
    return node


def profile() -> dict[str, Any]:
    c = load_config()["models"]
    return c["profiles"][c["profile"]]


def model_for(node: str) -> str:
    nodes = profile()["nodes"]
    return nodes.get(node) or nodes.get("default") or next(iter(nodes.values()))


def price_for(model: str) -> tuple[float, float]:
    p = cfg("models", "prices", default={}).get(model, [0.0, 0.0])
    return float(p[0]), float(p[1])


def prompt(name: str) -> str:
    """Prompts live in agent/prompts/<name>.md (versioned; CI checks nothing is inlined)."""
    return (ROOT / "agent" / "prompts" / f"{name}.md").read_text(encoding="utf-8")
