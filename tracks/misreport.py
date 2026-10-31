"""Track D: misreporting (C-9).

The pilot agent lies: it reports its favourite option as regret 0 and every other option as
regret 1 (exaggeration), and falsely claims minimum fuel to get priority weighting. We compare,
on the same scenarios, honest vs lying pilot, with the min-fuel claim verified or not.
Costs are measured with the TRUE cost model (full scenario), never the reported one.

  python -m tracks.misreport [--scenarios scenarios.jsonl] [--aggregation nash]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from protocol import run_episode, score_result
from tracks.common import load_scenarios

CONDITIONS = {
    "honest": ({"pilot": "scripted"}, True),
    "liar, claim verified": ({"pilot": "misreporting"}, True),
    "liar, claim unverified": ({"pilot": "misreporting"}, False),
}


def run(scenarios, disclosure="D2", aggregation="weighted_sum") -> list[dict]:
    rows = []
    for scn in scenarios:
        base = None
        for cond, (strategy, verify) in CONDITIONS.items():
            res = run_episode(scn, strategy=strategy, disclosure=disclosure, aggregation=aggregation,
                              verify_claims=verify)
            sc = score_result(scn, res)
            row = {"scenario": scn.scenario_id, "condition": cond, "status": res.status,
                   "option": res.option_id, "costs": sc["costs"], "global_cost_usd": sc["global_cost_usd"],
                   "claims": res.claims}
            if cond == "honest":
                base = row
            elif base and base["costs"] and row["costs"]:
                row["pilot_gain_usd"] = round(base["costs"]["pilot"] - row["costs"]["pilot"], 2)
                row["others_loss_usd"] = round(sum(row["costs"][r] - base["costs"][r] for r in ("atc", "ground")), 2)
                row["global_loss_usd"] = round(row["global_cost_usd"] - base["global_cost_usd"], 2)
            rows.append(row)
    return rows


def summarise(rows) -> str:
    out = []
    for cond in CONDITIONS:
        rs = [r for r in rows if r["condition"] == cond]
        line = f"{cond:<24} n={len(rs)}"
        if cond != "honest":
            g = [r for r in rs if "pilot_gain_usd" in r]
            if g:
                line += (f"  outcome changed={sum(r['pilot_gain_usd'] != 0 for r in g)}/{len(g)}"
                         f"  liar gain ${sum(r['pilot_gain_usd'] for r in g):,.0f}"
                         f"  others' loss ${sum(r['others_loss_usd'] for r in g):,.0f}"
                         f"  global loss ${sum(r['global_loss_usd'] for r in g):,.0f}")
            line += f"  false claims accepted={sum(c['accepted'] for r in rs for c in r['claims'])}"
        out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--disclosure", default="D2")
    ap.add_argument("--aggregation", default="weighted_sum")
    ap.add_argument("--out", default="runs/track_d.jsonl")
    a = ap.parse_args()
    rows = run(load_scenarios(a.scenarios, a.limit), a.disclosure, a.aggregation)
    Path(a.out).parent.mkdir(exist_ok=True)
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(summarise(rows))
    print(f"rows written to {a.out}")


if __name__ == "__main__":
    main()
