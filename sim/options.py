"""Deterministic option generator (B-1). Uses public data only, so the mediator and every
agent derive the same option list (and the same option IDs) from any view."""
from __future__ import annotations

from contracts import SIZE_ORDER, Option, PublicInfo, Scenario
from sim.simulate import EPS, earliest_landing_min

MAX_SLOTS_PER_ROUTE = 8


def fmt_time(minutes: float) -> str:
    """Destination-local clock time; hours can exceed 23 for next-day times."""
    h, m = divmod(minutes, 60)
    if abs(m - round(m)) < EPS:
        return f"{int(h):02d}:{round(m):02d}"
    return f"{int(h):02d}:{int(m):02d}:{round((m % 1) * 60):02d}"


def make_option_id(route_id: str, slot_min: float | None, absorption: str, gate_id: str | None) -> str:
    if slot_min is None:
        return f"{route_id}/divert"
    return f"{route_id}@{fmt_time(slot_min)}/{absorption}/{gate_id}"


def generate_options(scenario: Scenario | PublicInfo) -> list[Option]:
    public = scenario.public if isinstance(scenario, Scenario) else scenario
    focal = public.focal
    # Publicly obvious incompatibilities (gate too small, another airline's gate) are left out.
    # The ground agent's rules still re-check size and airline for anything proposed.
    gates = sorted(
        (g for g in public.gates
         if SIZE_ORDER[g.size] >= SIZE_ORDER[focal.size_class] and g.airline in (focal.airline, "COMMON")),
        key=lambda g: g.gate_id,
    )
    all_slots = sorted(set(public.available_slots_min) | {public.rbs_slot_min})
    pre_departure = public.decision_point == "pre_departure"

    options: list[Option] = []
    for route in public.routes:
        if route.diversion_airport:
            options.append(Option(option_id=make_option_id(route.route_id, None, "none", None),
                                  route_id=route.route_id, slot_min=None, absorption="none", gate_id=None))
            continue
        earliest = earliest_landing_min(public, route)
        reachable = [s for s in all_slots if s >= earliest - EPS]
        slots = reachable[:MAX_SLOTS_PER_ROUTE]
        if public.rbs_slot_min in reachable and public.rbs_slot_min not in slots:
            slots.append(public.rbs_slot_min)
        for slot in slots:
            if slot - earliest <= EPS:
                absorptions = ["none"]
            else:
                absorptions = ["ground", "airborne"] if pre_departure else ["airborne"]
            for absorption in absorptions:
                for gate in gates:
                    options.append(Option(
                        option_id=make_option_id(route.route_id, slot, absorption, gate.gate_id),
                        route_id=route.route_id, slot_min=slot, absorption=absorption, gate_id=gate.gate_id,
                    ))
    return options


def option_by_id(options: list[Option], option_id: str) -> Option:
    for o in options:
        if o.option_id == option_id:
            return o
    raise KeyError(option_id)
