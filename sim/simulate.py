"""Deterministic simulator: what happens if the focal flight follows an option.

Split by information boundary, so agents only ever compute with their own view:
- compute_timeline  -> public data only
- atc_outcome / pilot_outcome / ground_outcome -> public + that organisation's private data
- simulate          -> everything available in the given scenario (or view)

Invalid options (unknown route/gate, slot before the aircraft can land, wrong absorption)
raise ValueError. Only option IDs from `generate_options` should reach these functions.
"""
from __future__ import annotations

from contracts import (
    ATCOutcome, ATCPrivate, Gate, GroundOutcome, GroundPrivate, Option, Outcome, PilotOutcome,
    PilotPrivate, PublicInfo, RouteOption, Scenario, Timeline,
)
from sim.params import DIVERSION_RECOVERY_MIN, DIVERSION_TAXI_IN_MIN, wake_separation_min

EPS = 1e-6


def get_route(public: PublicInfo, route_id: str) -> RouteOption:
    for r in public.routes:
        if r.route_id == route_id:
            return r
    raise ValueError(f"unknown route {route_id!r}")


def get_gate(public: PublicInfo, gate_id: str) -> Gate:
    for g in public.gates:
        if g.gate_id == gate_id:
            return g
    raise ValueError(f"unknown gate {gate_id!r}")


def earliest_landing_min(public: PublicInfo, route: RouteOption) -> float:
    """Earliest possible landing on `route` with no delay absorbed."""
    if public.decision_point == "pre_departure":
        f = public.focal
        off_block = max(public.decision_time_min, f.sched_departure_min, public.ready_min or 0.0)
        wheels_off = off_block + f.taxi_out_min
        return wheels_off + route.air_time_min
    return public.decision_time_min + route.air_time_min


def compute_timeline(public: PublicInfo, option: Option) -> Timeline:
    route = get_route(public, option.route_id)
    pre_departure = public.decision_point == "pre_departure"
    earliest = earliest_landing_min(public, route)
    wheels_off = earliest - route.air_time_min if pre_departure else None

    if route.diversion_airport:
        if option.slot_min is not None or option.gate_id is not None:
            raise ValueError("a diversion option has no destination slot or gate")
        return Timeline(
            departure_min=wheels_off, landing_min=earliest, landing_airport=route.diversion_airport,
            in_block_min=earliest + DIVERSION_RECOVERY_MIN, ground_delay_min=0.0,
            airborne_holding_min=0.0,
            arrival_delay_min=earliest + DIVERSION_RECOVERY_MIN - public.focal.sched_arrival_min,
            is_diversion=True,
        )

    if option.slot_min is None or option.gate_id is None:
        raise ValueError("a non-diversion option needs a slot and a gate")
    delay = option.slot_min - earliest
    if delay < -EPS:
        raise ValueError(f"slot {option.slot_min} is before earliest landing {earliest:.1f}")
    delay = max(delay, 0.0)
    if delay > EPS and option.absorption == "none":
        raise ValueError("delay to slot must be absorbed on the ground or airborne")
    if option.absorption == "ground" and not pre_departure:
        raise ValueError("ground delay is impossible once airborne")

    ground = delay if option.absorption == "ground" else 0.0
    holding = delay if option.absorption == "airborne" else 0.0
    in_block = option.slot_min + get_gate(public, option.gate_id).taxi_in_min
    return Timeline(
        departure_min=None if wheels_off is None else wheels_off + ground,
        landing_min=option.slot_min, landing_airport=public.focal.destination,
        in_block_min=in_block, ground_delay_min=ground, airborne_holding_min=holding,
        arrival_delay_min=in_block - public.focal.sched_arrival_min, is_diversion=False,
    )


def _require(private, role: str):
    if private is None:
        raise ValueError(f"{role} private data is not in this view")
    return private


def atc_outcome(view: Scenario, option: Option, tl: Timeline | None = None) -> ATCOutcome:
    atc: ATCPrivate = _require(view.atc, "atc")
    tl = tl or compute_timeline(view.public, option)
    if tl.is_diversion:
        return ATCOutcome(leader_gap_min=None, leader_required_min=None, follower_gap_min=None,
                          follower_required_min=None, arrivals_in_hour=0, holding_min=0.0)

    me = view.public.focal.wake_category
    t = tl.landing_min
    leaders = [a for a in atc.arrival_sequence if a.slot_min <= t]
    followers = [a for a in atc.arrival_sequence if a.slot_min > t]
    leader = max(leaders, key=lambda a: a.slot_min, default=None)
    follower = min(followers, key=lambda a: a.slot_min, default=None)
    in_hour = sum(1 for a in atc.arrival_sequence if t - 60 < a.slot_min <= t) + 1  # rolling 60 min incl. us
    return ATCOutcome(
        leader_gap_min=None if leader is None else t - leader.slot_min,
        leader_required_min=None if leader is None else wake_separation_min(leader.wake_category, me),
        follower_gap_min=None if follower is None else follower.slot_min - t,
        follower_required_min=None if follower is None else wake_separation_min(me, follower.wake_category),
        arrivals_in_hour=in_hour, holding_min=tl.airborne_holding_min,
    )


def pilot_outcome(view: Scenario, option: Option, tl: Timeline | None = None) -> PilotOutcome:
    p: PilotPrivate = _require(view.pilot, "pilot")
    tl = tl or compute_timeline(view.public, option)
    route = get_route(view.public, option.route_id)
    nominal = get_route(view.public, "nominal")

    holding_fuel = tl.airborne_holding_min * p.holding_burn_kg_per_min
    reserve = p.final_reserve_min * p.holding_burn_kg_per_min
    required = reserve if tl.is_diversion else p.alternate_fuel_kg + reserve
    crew_off = tl.landing_min + DIVERSION_TAXI_IN_MIN if tl.is_diversion else tl.in_block_min
    missed = sum(c.pax for c in p.connections if tl.in_block_min + c.min_connect_min > c.departure_min)
    return PilotOutcome(
        fuel_at_landing_kg=p.fuel_on_board_kg - route.trip_fuel_kg - holding_fuel,
        required_landing_fuel_kg=required,
        extra_fuel_kg=route.trip_fuel_kg - nominal.trip_fuel_kg + holding_fuel,
        missed_connection_pax=missed,
        turbulence_min=route.turbulence_min,
        duty_margin_min=p.crew_duty_end_min - crew_off,
    )


def ground_outcome(view: Scenario, option: Option, tl: Timeline | None = None) -> GroundOutcome:
    g: GroundPrivate = _require(view.ground, "ground")
    tl = tl or compute_timeline(view.public, option)
    ready = tl.in_block_min + g.min_turnaround_min
    next_delay = max(0.0, ready - g.next_leg.sched_departure_min) if g.next_leg else 0.0
    if tl.is_diversion:
        # Aircraft comes back hours later; today's ramp shift and gate plan are not used.
        return GroundOutcome(gate_conflict_with=None, gate_changed=False, overtime_min=0.0,
                             next_leg_delay_min=next_delay)

    # Gate is held from in-block until the next leg actually leaves (or turnaround ends).
    release = max(ready, g.next_leg.sched_departure_min) if g.next_leg else ready
    conflict = next(
        (b.flight_id for b in sorted(g.gate_bookings, key=lambda b: b.start_min)
         if b.gate_id == option.gate_id and b.start_min < release and tl.in_block_min < b.end_min),
        None,
    )
    # The crew on shift at block-in finishes the turn; arriving after shift end, the next shift takes it.
    overtime = max(0.0, ready - g.crew_shift_end_min) if tl.in_block_min < g.crew_shift_end_min else 0.0
    return GroundOutcome(
        gate_conflict_with=conflict,
        gate_changed=option.gate_id != g.planned_gate_id,
        overtime_min=overtime,
        next_leg_delay_min=next_delay,
    )


def simulate(scenario: Scenario, option: Option) -> Outcome:
    """Everything computable from `scenario`; private parts missing from a view stay None."""
    tl = compute_timeline(scenario.public, option)
    return Outcome(
        timeline=tl,
        atc=atc_outcome(scenario, option, tl) if scenario.atc else None,
        pilot=pilot_outcome(scenario, option, tl) if scenario.pilot else None,
        ground=ground_outcome(scenario, option, tl) if scenario.ground else None,
    )
