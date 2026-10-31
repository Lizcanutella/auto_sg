"""Siloed status quo vs FCFS/RBS (coordinated simple rules) vs best possible, over a scenarios file.

  siloed - best   = the price of silos (what today's uncoordinated process loses)
  fcfs   - best   = what is left once everyone shares data but follows simple rules
  share recovered = (siloed - fcfs) / (siloed - best): how much of the price sharing alone recovers

Run:  python -m bench.baselines_report data/scenarios.jsonl
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from baselines import best_possible, fcfs_rbs, siloed
from contracts import Scenario


def run(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.open():
        s = Scenario.model_validate_json(line)
        sil, f, b = siloed.plan(s), fcfs_rbs.plan(s), best_possible.plan(s)
        focal = s.public.focal
        cost = lambda r: r.chosen.global_cost_usd if r.chosen else None
        rows.append({
            "scenario_id": s.scenario_id, "dest": focal.destination,
            "cause": "weather" if focal.recorded_weather_delay_min > 15 else "late_aircraft",
            "n_options": b.n_options, "n_feasible": b.n_feasible, "status": b.status,
            "siloed_usd": cost(sil), "fcfs_usd": cost(f), "best_usd": cost(b),
            "siloed_holding_min": sil.chosen.outcome.timeline.airborne_holding_min if sil.chosen else None,
            "siloed_option": sil.chosen.option.option_id if sil.chosen else None,
            "best_option": b.chosen.option.option_id if b.chosen else None,
        })
    d = pd.DataFrame(rows)
    d["price_of_silos_usd"] = d.siloed_usd - d.best_usd
    d["fcfs_gap_usd"] = d.fcfs_usd - d.best_usd
    return d


def summary(d: pd.DataFrame) -> pd.DataFrame:
    plan = d[d.status == "plan"]
    g = plan.groupby("cause")
    out = g.agg(n=("best_usd", "size"),
                silos_gt0=("price_of_silos_usd", lambda x: (x > 0.5).mean()),
                mean_price_of_silos=("price_of_silos_usd", "mean"),
                mean_siloed_holding_min=("siloed_holding_min", "mean"),
                fcfs_gt0=("fcfs_gap_usd", lambda x: (x > 0.5).mean()),
                mean_fcfs_gap=("fcfs_gap_usd", "mean"))
    totals = g[["siloed_usd", "fcfs_usd", "best_usd"]].sum()
    out["share_recovered_by_sharing"] = (totals.siloed_usd - totals.fcfs_usd) / (totals.siloed_usd - totals.best_usd)
    return out.round(2)


if __name__ == "__main__":
    d = run(Path(sys.argv[1] if len(sys.argv) > 1 else "data/scenarios.jsonl"))
    print(f"scenarios {len(d)} | escalate {(d.status == 'escalate').sum()} | median options {d.n_options.median():.0f}"
          f" | median feasible {d.n_feasible.median():.0f}")
    print(summary(d).to_string())
