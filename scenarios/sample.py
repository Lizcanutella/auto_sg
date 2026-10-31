"""Stratified sample of focal rows -> data/scenarios.jsonl (A-2).

Strata: cause (weather vs late aircraft only) x destination size class, equal-sized cells,
because weather rows are only ~12% of flights.csv and large hubs would otherwise dominate.

Run:  python -m scenarios.sample --n 500 --seed 7
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scenarios.build import build_scenario
from scenarios.flights import flight_index
from scenarios.workbook import load_workbook

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "scenarios.jsonl"


def stratified_rows(df: pd.DataFrame, size_class: pd.Series, n: int, seed: int) -> pd.DataFrame:
    cells = df.assign(_cause=df.is_weather.map({True: "weather", False: "late_aircraft"}), _size=size_class)
    groups = list(cells.groupby(["_cause", "_size"]))
    per_cell = -(-n // len(groups))
    picked = [g.sample(min(per_cell, len(g)), random_state=seed) for _, g in groups]
    return pd.concat(picked).sample(frac=1, random_state=seed).head(n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    wb = load_workbook()
    idx = flight_index()
    df = idx.df
    size_class = df.DESTINATION_AIRPORT.map(lambda a: wb.airports[a].size_class)
    rows = stratified_rows(df, size_class, args.n, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    index = []
    with args.out.open("w") as f:
        for i, (row_id, row) in enumerate(rows.iterrows()):
            s = build_scenario(row, idx, wb, seed=args.seed * 1_000_003 + int(row_id), scenario_id=f"A{i:04d}")
            f.write(s.model_dump_json() + "\n")
            n_real = sum(1 for a in s.atc.arrival_sequence if not a.flight_id.startswith("SYN-"))
            index.append({"scenario_id": s.scenario_id, "flight_id": row.flight_id, "row": int(row_id),
                          "dest": row.DESTINATION_AIRPORT, "size_class": size_class[row_id],
                          "cause": "weather" if row.is_weather else "late_aircraft",
                          "real_neighbours": n_real, "next_leg": s.provenance["ground.next_leg"].value})
    pd.DataFrame(index).to_csv(args.out.with_name(args.out.stem + "_index.csv"), index=False)
    print(json.dumps({"written": len(index), "out": str(args.out)}))


if __name__ == "__main__":
    main()
