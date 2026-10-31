"""FCFS / Ration-by-Schedule baseline (B-5): a stand-in for today's phone-based process.

The focal flight keeps its RBS slot if anything works there. Otherwise the dispatcher works
through options in a fixed order and takes the first one every organisation can accept:
  slot: RBS slot, then later slots, then earlier holes (compression happens last, if at all)
  route: nominal first, then published alternatives; diversion only as a last resort
  delay: on the ground before airborne holding
  gate: planned gate first, then by gate ID
It sees all private data (humans on the phone can ask), but never optimises cost.
"""
from __future__ import annotations

from contracts import EvaluatedOption, PlanResult, Scenario
from sim.evaluate import evaluate_all
from sim.params import DEFAULT_COSTS, CostParams

METHOD = "fcfs_rbs"
_ABSORPTION_ORDER = {"none": 0, "ground": 1, "airborne": 2}


def plan(scenario: Scenario, p: CostParams = DEFAULT_COSTS) -> PlanResult:
    evaluated = evaluate_all(scenario, p)
    feasible = [e for e in evaluated if e.feasible]
    ordered = sorted(feasible, key=lambda e: _dispatch_order(scenario, e))
    if not ordered:
        return PlanResult(method=METHOD, status="escalate", chosen=None, n_options=len(evaluated),
                          n_feasible=0, reason="no option satisfies every organisation's hard constraints")
    return PlanResult(method=METHOD, status="plan", chosen=ordered[0], n_options=len(evaluated),
                      n_feasible=len(feasible))


def _dispatch_order(scenario: Scenario, e: EvaluatedOption) -> tuple:
    o = e.option
    public = scenario.public
    route_rank = [r.route_id for r in public.routes].index(o.route_id)
    if o.slot_min is None:                          # diversion
        return (3, 0.0, route_rank, 0, "")
    rbs = public.rbs_slot_min
    slot_group = 0 if o.slot_min == rbs else 1 if o.slot_min > rbs else 2
    nominal_first = 0 if o.route_id == "nominal" else 1
    planned = scenario.ground.planned_gate_id if scenario.ground else None
    gate_rank = (0 if o.gate_id == planned else 1, o.gate_id)
    return (slot_group, o.slot_min, nominal_first, route_rank, _ABSORPTION_ORDER[o.absorption], gate_rank)
