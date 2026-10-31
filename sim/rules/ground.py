"""Ground-handling hard constraints: gate free, gate size, gate airline, ramp crew overtime cap."""
from __future__ import annotations

from contracts import SIZE_ORDER, Option, RuleResult, Scenario, Timeline
from sim import params
from sim.rules._common import not_applicable, rule
from sim.simulate import EPS, compute_timeline, get_gate, ground_outcome

ROLE = "ground"
RULE_IDS = ("GND-GATE-FREE", "GND-GATE-SIZE", "GND-GATE-AIRLINE", "GND-CREW")


def check(view: Scenario, option: Option, tl: Timeline | None = None) -> list[RuleResult]:
    tl = tl or compute_timeline(view.public, option)
    o = ground_outcome(view, option, tl)
    g = view.ground
    if tl.is_diversion:
        return [not_applicable(ROLE, r, "diversion: no hub gate or ramp crew needed today") for r in RULE_IDS]

    focal = view.public.focal
    gate = get_gate(view.public, option.gate_id)
    size_ok = SIZE_ORDER[gate.size] >= SIZE_ORDER[focal.size_class]
    return [
        rule(ROLE, "GND-GATE-FREE", o.gate_conflict_with is None, None, None, "", params.GATE_SOURCE,
             f"gate {gate.gate_id} " + (f"occupied by {o.gate_conflict_with}" if o.gate_conflict_with else "is free")),
        rule(ROLE, "GND-GATE-SIZE", size_ok, None, None, "", params.GATE_SOURCE,
             f"gate {gate.gate_id} takes up to {gate.size.value}, aircraft is {focal.size_class.value}"),
        rule(ROLE, "GND-GATE-AIRLINE", gate.airline in (focal.airline, "COMMON"), None, None, "",
             params.GATE_SOURCE, f"gate {gate.gate_id} belongs to {gate.airline}"),
        rule(ROLE, "GND-CREW", o.overtime_min <= g.max_overtime_min + EPS, round(o.overtime_min, 1),
             g.max_overtime_min, "min", params.CREW_SOURCE, "ramp crew overtime vs cap"),
    ]
