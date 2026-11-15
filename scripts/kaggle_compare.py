"""Compare GigSim's synthetic market statistics with REAL Upwork postings (Kaggle: asaniczka/
upwork-job-postings-dataset-2024-50k-records). Only aggregates are written; the raw CSV stays in data/raw/
(git-ignored). GigSim's seed is NOT regenerated (it is frozen and the dev labels depend on it).

    python -m scripts.kaggle_compare data/raw/kaggle_upwork2024/upwork-jobs.csv
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

from scripts.gen.jobs import _cat_from_text

ROOT = Path(__file__).resolve().parents[1]


def pct(xs, qs=(25, 40, 50, 75)):
    return [round(float(v), 2) for v in np.percentile(xs, qs)] if len(xs) >= 20 else None


def main(path: str) -> None:
    rows = list(csv.DictReader(open(path, encoding="utf-8", errors="ignore")))
    by: dict[str, dict[str, list]] = {}
    for r in rows:
        cat, _ = _cat_from_text(r["title"] or "")
        b = by.setdefault(cat, {"hourly_mid": [], "fixed": [], "n": []})
        b["n"].append(1)
        try:
            if r["is_hourly"] == "True" and r["hourly_low"] and r["hourly_high"]:
                mid = (float(r["hourly_low"]) + float(r["hourly_high"])) / 2
                if 3 <= mid <= 300:
                    b["hourly_mid"].append(mid)
            elif r["budget"]:
                v = float(r["budget"])
                if 5 <= v <= 100000:
                    b["fixed"].append(v)
        except ValueError:
            continue
    synth = json.loads((ROOT / "gigsim" / "seed" / "market_stats.json").read_text(encoding="utf-8"))
    out = {}
    for cat in ["ai_ml", "web", "data", "other"]:
        b = by.get(cat, {"hourly_mid": [], "fixed": [], "n": []})
        real_h = pct(b["hourly_mid"])
        s = synth[cat]
        syn_h = [s["hourly_p25"], s["hourly_p40"], s["hourly_p50"], s["hourly_p75"]]
        out[cat] = {"real_jobs": len(b["n"]), "real_hourly_jobs": len(b["hourly_mid"]), "real_fixed_jobs": len(b["fixed"]),
                    "real_hourly_p25_p40_p50_p75": real_h, "synthetic_hourly_p25_p40_p50_p75": syn_h,
                    "synthetic_over_real_p50": round(syn_h[2] / real_h[2], 2) if real_h else None,
                    "real_fixed_p25_p50_p75": pct(b["fixed"], (25, 50, 75))}
    res = {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "Kaggle asaniczka/upwork-job-postings-dataset-2024-50k-records (real postings, Feb 2024)",
                    "rows": len(rows), "categoriser": "scripts/gen/jobs.py::_cat_from_text (title keywords)",
                    "note": "aggregates only; GigSim seed not regenerated (frozen; dev labels depend on it)"},
           "by_category": out}
    p = ROOT / "evals" / "results" / "kaggle_market_comparison.json"
    p.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for c, v in out.items():
        print(c, v["real_jobs"], "real p50 $/h", (v["real_hourly_p25_p40_p50_p75"] or [None] * 3)[2], "synthetic p50",
              v["synthetic_hourly_p25_p40_p50_p75"][2], "ratio", v["synthetic_over_real_p50"])


if __name__ == "__main__":
    main(sys.argv[1])
