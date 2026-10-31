"""One-call evaluation of options: outcome + rule results + costs. Used by baselines and the benchmark."""
from __future__ import annotations

from contracts import EvaluatedOption, Option, Scenario
from sim.costs import all_costs, global_cost
from sim.options import generate_options
from sim.params import DEFAULT_COSTS, CostParams
from sim.rules import check_all
from sim.simulate import simulate


def evaluate(scenario: Scenario, option: Option, p: CostParams = DEFAULT_COSTS) -> EvaluatedOption:
    outcome = simulate(scenario, option)
    rules = check_all(scenario, option)
    costs = all_costs(scenario, option, p, outcome.timeline)
    return EvaluatedOption(
        option=option, outcome=outcome, rule_results=rules, costs=costs,
        global_cost_usd=round(global_cost(costs, p), 2), feasible=all(r.passed for r in rules),
    )


def evaluate_all(scenario: Scenario, p: CostParams = DEFAULT_COSTS) -> list[EvaluatedOption]:
    return [evaluate(scenario, o, p) for o in generate_options(scenario)]
