"""Private cost per organisation and the global objective (B-3). All values in USD.

Every cost component belongs to exactly one organisation, so the global cost (weighted sum
over organisations) never double counts.
"""
from __future__ import annotations

from contracts import ROLES, CostBreakdown, Option, Role, Scenario, Timeline
from sim.params import DEFAULT_COSTS, CostParams
from sim.simulate import atc_outcome, compute_timeline, ground_outcome, pilot_outcome


def atc_cost(view: Scenario, option: Option, p: CostParams = DEFAULT_COSTS,
             tl: Timeline | None = None) -> CostBreakdown:
    tl = tl or compute_timeline(view.public, option)
    o = atc_outcome(view, option, tl)
    rerouted = option.route_id != "nominal" and not tl.is_diversion
    return _breakdown("atc", {
        "holding": o.holding_min * p.holding_usd_per_min,
        "reroute_coordination": p.reroute_coordination_usd if rerouted else 0.0,
        "unused_rbs_slot": p.unused_rbs_slot_usd if option.slot_min != view.public.rbs_slot_min else 0.0,
    })


def pilot_cost(view: Scenario, option: Option, p: CostParams = DEFAULT_COSTS,
               tl: Timeline | None = None) -> CostBreakdown:
    tl = tl or compute_timeline(view.public, option)
    o = pilot_outcome(view, option, tl)
    return _breakdown("pilot", {
        "arrival_delay": max(0.0, tl.arrival_delay_min) * p.delay_usd_per_min,
        "fuel": o.extra_fuel_kg * p.fuel_usd_per_kg,
        "missed_connections": o.missed_connection_pax * p.missed_connection_usd_per_pax,
        "turbulence": o.turbulence_min * p.turbulence_usd_per_min,
        "diversion": p.diversion_fixed_usd if tl.is_diversion else 0.0,
    })


def ground_cost(view: Scenario, option: Option, p: CostParams = DEFAULT_COSTS,
                tl: Timeline | None = None) -> CostBreakdown:
    tl = tl or compute_timeline(view.public, option)
    o = ground_outcome(view, option, tl)
    return _breakdown("ground", {
        "overtime": o.overtime_min * view.ground.ramp_crew_size * p.ramp_usd_per_crew_min * p.overtime_multiplier,
        "gate_change": p.gate_change_usd if o.gate_changed else 0.0,
        "knock_on_delay": o.next_leg_delay_min * p.knock_on_delay_usd_per_min,
    })


COST_FUNCTIONS = {"atc": atc_cost, "pilot": pilot_cost, "ground": ground_cost}


def role_cost(role: Role, view: Scenario, option: Option, p: CostParams = DEFAULT_COSTS,
              tl: Timeline | None = None) -> CostBreakdown:
    return COST_FUNCTIONS[role](view, option, p, tl)


def global_cost(costs: dict[str, CostBreakdown], p: CostParams = DEFAULT_COSTS) -> float:
    weights = {"atc": p.weight_atc, "pilot": p.weight_pilot, "ground": p.weight_ground}
    return sum(weights[role] * c.total_usd for role, c in costs.items())


def all_costs(scenario: Scenario, option: Option, p: CostParams = DEFAULT_COSTS,
              tl: Timeline | None = None) -> dict[str, CostBreakdown]:
    tl = tl or compute_timeline(scenario.public, option)
    return {role: role_cost(role, scenario, option, p, tl) for role in ROLES if getattr(scenario, role) is not None}


def _breakdown(role: Role, components: dict[str, float]) -> CostBreakdown:
    components = {k: round(v, 2) for k, v in components.items()}
    return CostBreakdown(role=role, components_usd=components, total_usd=round(sum(components.values()), 2))
