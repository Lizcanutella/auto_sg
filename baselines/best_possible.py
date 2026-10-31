"""Best-possible reference (B-6): a central planner that sees every organisation's private data
and picks the feasible option with the lowest global cost. Equivalent to disclosure level D3."""
from __future__ import annotations

from contracts import PlanResult, Scenario
from sim.evaluate import evaluate_all
from sim.params import DEFAULT_COSTS, CostParams

METHOD = "best_possible"


def plan(scenario: Scenario, p: CostParams = DEFAULT_COSTS) -> PlanResult:
    evaluated = evaluate_all(scenario, p)
    feasible = [e for e in evaluated if e.feasible]
    if not feasible:
        return PlanResult(method=METHOD, status="escalate", chosen=None, n_options=len(evaluated),
                          n_feasible=0, reason="no option satisfies every organisation's hard constraints")
    best = min(feasible, key=lambda e: (e.global_cost_usd, e.option.option_id))
    return PlanResult(method=METHOD, status="plan", chosen=best, n_options=len(evaluated),
                      n_feasible=len(feasible))
