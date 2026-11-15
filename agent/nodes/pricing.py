"""Pricing Strategist: bid from market statistics, client budget and the user's floor; is the Connects cost worth it?"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from ..handoffs import PriceQuote
from ._base import deps, node

USD_PER_CONNECT = 0.15


def quote(job: dict, spec: dict, stats: dict | None, profile, fit: float, balance: int | None,
          connects_cost: int) -> PriceQuote:
    hours = float(spec.get("est_hours") or 40)
    p40 = (stats or {}).get("hourly_p40") or profile.hourly_rate * 0.9
    p75 = (stats or {}).get("hourly_p75") or profile.hourly_rate * 1.2
    p50 = (stats or {}).get("hourly_p50") or profile.hourly_rate
    notes = []
    if job.get("budget_type") == "hourly":
        hi = (job.get("hourly_range") or [None, p75])[1] or p75
        rate = min(max(profile.hourly_rate, p40), p75, hi)
        rate = max(rate, profile.floor_rate)
        notes.append(f"Your rate ${profile.hourly_rate}/h clamped to market p40-p75 (${p40:.0f}-${p75:.0f}) "
                     f"and the client's max ${hi}/h.")
        amount, lo, hi_band = round(rate), round(p40), round(p75)
        bid_type = "hourly"
    else:
        lo, hi_band = hours * p40, hours * p75
        target = (lo + hi_band) / 2
        budget = job.get("budget")
        if budget:
            target = min(target, budget) if budget >= lo else budget
            notes.append(f"Client budget ${budget:,.0f}; fair band ${lo:,.0f}-${hi_band:,.0f} for ~{hours:.0f}h.")
        else:
            notes.append(f"No fixed budget; fair band ${lo:,.0f}-${hi_band:,.0f} for ~{hours:.0f}h.")
        floor_total = max(profile.min_project, hours * profile.floor_rate * 0.8)
        target = max(target, floor_total)
        if budget and target > budget:
            # never bid above the client's own budget (failure analysis: job-dev-ai-071 bid 97% over the ceiling);
            # say plainly that the budget is below the user's floor for this scope instead
            notes.append(f"Budget is below your floor for ~{hours:.0f}h (${floor_total:,.0f}); bidding at the budget — "
                         "propose a reduced first milestone.")
            target = budget
        amount, bid_type = round(target, -1), "fixed"
    p_win = 0.04 + 0.22 * fit
    value = p_win * (amount * (hours if bid_type == "hourly" else 1)) * 0.15
    cost_usd = connects_cost * USD_PER_CONNECT
    worth = value > cost_usd and (balance is None or balance >= connects_cost)
    if balance is not None and balance < connects_cost:
        notes.append(f"Not enough Connects ({balance} < {connects_cost}).")
    notes.append(f"Connects {connects_cost} (~${cost_usd:.2f}) vs expected value ~${value:,.0f} (p_win≈{p_win:.0%}).")
    return PriceQuote(bid_type=bid_type, amount=float(amount), band_low=round(lo, 2), band_high=round(hi_band, 2),
                      market_hourly_p50=p50, est_hours=hours, connects_cost=connects_cost, connects_worth_it=worth,
                      rationale=" ".join(notes))


@node("pricing", timeout_s=45)
async def pricing(state: dict, config: RunnableConfig) -> dict:
    d = deps(config)
    job = state["job"]
    stats = await d.port.get_market_stats("pricing", job.get("category") or "other")
    bal = (await d.port.get_connects_balance("pricing")).get("balance")
    q = quote(job, state.get("job_spec", {}), stats, d.profile, state.get("fit", {}).get("score", 0.5), bal,
              int(job.get("connects_cost") or 0))
    policy = await d.port.get_policy("pricing")  # handed to the Compliance Guard via state (it has no MCP access)
    return {"price": q.model_dump(), "policy": policy}
