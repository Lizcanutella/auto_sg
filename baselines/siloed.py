"""Siloed status-quo baseline: each organisation decides its own part with only its own data,
in sequence, and they only talk ("phone call") when a hard limit is hit.

  1. ATC assigns the RBS slot (then later slots, then earlier holes, if a call rejects it).
  2. The airline is not linked to the slot list (no CDM): it departs when ready on the nominal
     route and absorbs the delay to the slot by HOLDING IN THE AIR. Ground delay happens only
     after a call, when holding breaks a fuel or holding-stack limit.
  3. Ground keeps the planned gate, otherwise the first free gate by ID. It knows nothing of
     connections, fuel or turbulence.
Every proposed combination is checked against all hard rules (that is the phone call), so the
plan is always safe. It is never cost-optimised. `reason` reports how many calls it took.

ASSUMPTION (state in the demo): slot updates reach the airline too late to hold it on the ground.
This is the brief's "excessive holding patterns and fuel consumption".
"""
from __future__ import annotations

from contracts import EvaluatedOption, PlanResult, Scenario
from sim.evaluate import evaluate_all
from sim.params import DEFAULT_COSTS, CostParams

METHOD = "siloed"
_ABSORPTION_ORDER = {"airborne": 0, "none": 1, "ground": 2}   # holding first: no one told the airline to wait


def plan(scenario: Scenario, p: CostParams = DEFAULT_COSTS) -> PlanResult:
    evaluated = evaluate_all(scenario, p)
    ordered = sorted(evaluated, key=lambda e: _sequence(scenario, e))
    calls = 0
    for e in ordered:
        if e.feasible:
            return PlanResult(method=METHOD, status="plan", chosen=e, n_options=len(evaluated),
                              n_feasible=sum(x.feasible for x in evaluated),
                              reason=f"accepted after {calls} rejected proposals (phone calls)")
        calls += 1
    return PlanResult(method=METHOD, status="escalate", chosen=None, n_options=len(evaluated), n_feasible=0,
                      reason=f"no safe plan after {calls} phone calls")


def _sequence(scenario: Scenario, e: EvaluatedOption) -> tuple:
    o = e.option
    public = scenario.public
    route_rank = [r.route_id for r in public.routes].index(o.route_id)
    if o.slot_min is None:                          # diversion: last resort
        return (3, 0.0, 0, route_rank, 0, (0, ""))
    rbs = public.rbs_slot_min
    slot_group = 0 if o.slot_min == rbs else 1 if o.slot_min > rbs else 2
    nominal_first = 0 if o.route_id == "nominal" else 1
    planned = scenario.ground.planned_gate_id
    return (slot_group, o.slot_min, nominal_first, route_rank, _ABSORPTION_ORDER[o.absorption],
            (0 if o.gate_id == planned else 1, o.gate_id))
