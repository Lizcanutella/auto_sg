"""Pilot / airline hard constraints: landing fuel, crew duty, convective weather."""
from __future__ import annotations

from contracts import Option, RuleResult, Scenario, Timeline
from sim import params
from sim.rules._common import rule
from sim.simulate import compute_timeline, get_route, pilot_outcome

ROLE = "pilot"
RULE_IDS = ("PILOT-FUEL", "PILOT-DUTY", "PILOT-WX")


def check(view: Scenario, option: Option, tl: Timeline | None = None) -> list[RuleResult]:
    tl = tl or compute_timeline(view.public, option)
    o = pilot_outcome(view, option, tl)
    route = get_route(view.public, option.route_id)
    fuel_what = "final reserve" if tl.is_diversion else "alternate + final reserve"
    return [
        rule(ROLE, "PILOT-FUEL", o.fuel_at_landing_kg >= o.required_landing_fuel_kg,
             round(o.fuel_at_landing_kg, 1), round(o.required_landing_fuel_kg, 1), "kg",
             params.FUEL_SOURCE, f"fuel at landing at {tl.landing_airport} vs {fuel_what}"),
        rule(ROLE, "PILOT-DUTY", o.duty_margin_min >= 0, round(o.duty_margin_min, 1), 0.0, "min",
             params.DUTY_SOURCE, "crew duty margin at block-in"),
        rule(ROLE, "PILOT-WX", not route.through_weather, None, None, "", params.WEATHER_SOURCE,
             f"route {route.route_id} " + ("crosses" if route.through_weather else "avoids") + " convective cells"),
    ]
