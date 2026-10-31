"""Track B (A-9): scenarios with no safe plan. The system must ESCALATE, never force a plan.

Each one starts from a real, solvable track-A scenario and changes one thing so that every
option breaks a hard rule:
  crew_timeout  - crew duty ends 10 min before the earliest possible block-in   (PILOT-DUTY)
  fuel_short    - fuel on board leaves less than the final reserve on any route  (PILOT-FUEL)
  no_gate       - every gate is booked for the whole option horizon             (GND-GATE-FREE)
  airport_cut   - every taxiway zone is closed, so no gate is reachable         (ATC-TWY)
The change is tagged in `provenance` as `track_b:<kind>` (synthetic). Track A also contains
scenarios that escalate naturally (mostly crews timing out after long delays).

Run:  python -m scenarios.track_b --per-kind 5
"""
from __future__ import annotations

import argparse
from pathlib import Path

from baselines import best_possible
from contracts import GateBooking, Provenance, Scenario
from sim import compute_timeline, generate_options

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("crew_timeout", "fuel_short", "no_gate", "airport_cut")


def make_infeasible(s: Scenario, kind: str) -> Scenario:
    opts = generate_options(s)
    in_blocks = [compute_timeline(s.public, o).in_block_min for o in opts]
    if kind == "crew_timeout":
        s = s.model_copy(update={"pilot": s.pilot.model_copy(update={"crew_duty_end_min": min(in_blocks) - 10.0})})
    elif kind == "fuel_short":
        reserve = s.pilot.final_reserve_min * s.pilot.holding_burn_kg_per_min + s.pilot.alternate_fuel_kg
        trip = min(r.trip_fuel_kg for r in s.public.routes)
        s = s.model_copy(update={"pilot": s.pilot.model_copy(update={"fuel_on_board_kg": trip + reserve - 1.0})})
    elif kind == "no_gate":
        lo, hi = min(in_blocks) - 60.0, max(in_blocks) + 600.0
        blocks = [GateBooking(gate_id=g.gate_id, flight_id=f"SYN-BLOCK-{g.gate_id}", start_min=lo, end_min=hi)
                  for g in s.public.gates]
        s = s.model_copy(update={"ground": s.ground.model_copy(
            update={"gate_bookings": [*s.ground.gate_bookings, *blocks]})})
    elif kind == "airport_cut":
        zones = sorted({g.zone for g in s.public.gates})
        s = s.model_copy(update={"atc": s.atc.model_copy(update={"closed_taxiway_zones": zones})})
    else:
        raise ValueError(kind)
    return s.model_copy(update={"track": "B", "provenance": {**s.provenance, f"track_b:{kind}": Provenance.SYNTHETIC}})


def build(scenarios: list[Scenario], per_kind: int) -> list[Scenario]:
    solvable = [s for s in scenarios if best_possible.plan(s).status == "plan"]
    out = []
    for k, kind in enumerate(KINDS):
        for i, base in enumerate(solvable[k * per_kind:(k + 1) * per_kind]):   # a different real row per variant
            b = make_infeasible(base, kind).model_copy(update={"scenario_id": f"B-{kind}-{base.scenario_id}"})
            assert best_possible.plan(b).status == "escalate", f"{b.scenario_id} still has a safe plan"
            out.append(b)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=ROOT / "data" / "scenarios.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "scenarios_track_b.jsonl")
    ap.add_argument("--per-kind", type=int, default=5)
    a = ap.parse_args()
    src = [Scenario.model_validate_json(l) for l in a.source.open()]
    b = build(src, a.per_kind)
    a.out.write_text("".join(s.model_dump_json() + "\n" for s in b))
    natural = sum(1 for s in src if best_possible.plan(s).status == "escalate")
    print(f"wrote {len(b)} track-B scenarios to {a.out}; track A also has {natural} natural escalations")


if __name__ == "__main__":
    main()
