"""Simulation core (workstream B). Public API for agents, mediator and benchmark:

    generate_options(scenario_or_view)          -> list[Option]       (same IDs from any view)
    check(role, view, option)                   -> list[RuleResult]   (role's hard constraints)
    role_cost(role, view, option, params)       -> CostBreakdown      (role's private cost, USD)
    simulate(scenario_or_view, option)          -> Outcome
    evaluate(scenario, option) / evaluate_all(scenario) -> EvaluatedOption(s)   (full scenario)

Agents must call these with `scenario.view(role)`, never the full scenario.
"""
from sim.costs import global_cost, role_cost
from sim.evaluate import evaluate, evaluate_all
from sim.options import fmt_time, generate_options, option_by_id
from sim.params import DEFAULT_COSTS, CostParams
from sim.rules import check, check_all, violations
from sim.simulate import compute_timeline, simulate

__all__ = [
    "DEFAULT_COSTS", "CostParams", "check", "check_all", "compute_timeline", "evaluate", "evaluate_all",
    "fmt_time", "generate_options", "global_cost", "option_by_id", "role_cost", "simulate", "violations",
]
