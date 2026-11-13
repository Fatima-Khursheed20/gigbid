"""Regenerate every synthetic artefact deterministically.

    python -m scripts.gen.run_all

Outputs (all SYNTHETIC unless noted):
  data/personas/<persona>/...        portfolio corpora (CV PDF, case studies, repos, reviews, proposals)
  gigsim/seed/*.json                 clients, historical jobs (Kaggle-derived titles/budgets when available),
                                     market stats, dev-pool jobs, live stream jobs
  evals/datasets/dev_<persona>.jsonl labelled dev set (gold labels by construction)
  data/heldout/                      self-held-out test set (git-ignored, new clients, different seed)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .jobs import (make_clients, make_historical, make_past_proposals, make_set, make_stream, market_stats)
from .personas import PERSONAS
from .render import render_persona

ROOT = Path(__file__).resolve().parents[2]


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def _jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def hidden_prefs_for(job: dict, client: dict, rng: random.Random) -> dict:
    skills = job.get("gold", {}).get("required_skills") or []
    ceiling = (job["budget"] * rng.uniform(1.0, 1.25)) if job.get("budget") else None
    hourly_ceiling = (job["hourly_range"][1] * rng.uniform(1.0, 1.15)) if job.get("hourly_range") else None
    return {"must_have": skills[:2], "budget_ceiling": ceiling, "hourly_ceiling": hourly_ceiling,
            **client["hidden_prefs"]}


def main() -> None:
    rng = random.Random(2026)
    for persona in PERSONAS:
        render_persona(persona, ROOT / "data" / "personas")
    clients = make_clients(rng, 400, "cl")
    legit = [c for c in clients if not c["scam"]]
    scam = [c for c in clients if c["scam"]]
    kaggle = ROOT / "data" / "processed" / "kaggle_jobs.json"
    hist = make_historical(rng, clients, 1500, kaggle)
    stats = market_stats(hist)
    seed = ROOT / "gigsim" / "seed"
    _dump(seed / "historical_jobs.json", hist)
    _dump(seed / "market_stats.json", stats)

    dev_pool, by_id = [], {c["client_id"]: c for c in clients}
    prng = random.Random(99)
    for persona in PERSONAS:
        props = make_past_proposals(random.Random(f"props-{persona}"), persona, hist)
        _jsonl(ROOT / "data" / "personas" / persona / "proposals.jsonl", props)
        dev = make_set("dev", persona, 200, legit, scam, stats)
        _jsonl(ROOT / "evals" / "datasets" / f"dev_{persona}.jsonl", dev)
        for j in dev:
            pub = {k: v for k, v in j.items() if k != "gold"}
            pub["_hidden"] = hidden_prefs_for(j, by_id[j["client_id"]], prng)
            pub["pool"] = "dev"
            dev_pool.append(pub)
    stream = make_stream(random.Random(7), legit, scam, stats, 300)
    for j in stream:
        j["_hidden"] = hidden_prefs_for({**j, "gold": {"required_skills": []}}, by_id[j["client_id"]], prng)
        j["pool"] = "stream"
    _dump(seed / "dev_jobs.json", dev_pool)
    _dump(seed / "stream_jobs.json", stream)
    _dump(seed / "clients.json", clients)

    # Self-held-out set: new clients, new seed. Git-ignored; touched once for the final report.
    hclients = make_clients(random.Random(4242), 150, "hc")
    hl = [c for c in hclients if not c["scam"]]
    hs = [c for c in hclients if c["scam"]]
    held_pool, hby = [], {c["client_id"]: c for c in hclients}
    for persona in PERSONAS:
        hset = make_set("heldout", persona, 60, hl, hs, stats)
        _jsonl(ROOT / "data" / "heldout" / f"heldout_{persona}.jsonl", hset)
        for j in hset:
            pub = {k: v for k, v in j.items() if k != "gold"}
            pub["_hidden"] = hidden_prefs_for(j, hby[j["client_id"]], prng)
            pub["pool"] = "heldout"
            held_pool.append(pub)
    _dump(ROOT / "data" / "heldout" / "heldout_jobs.json", held_pool)
    _dump(ROOT / "data" / "heldout" / "heldout_clients.json", hclients)
    n_k = sum(h["source"] == "kaggle" for h in hist)
    print(f"historical={len(hist)} (kaggle={n_k}) dev={len(dev_pool)} stream={len(stream)} heldout={len(held_pool)}")


if __name__ == "__main__":
    main()
