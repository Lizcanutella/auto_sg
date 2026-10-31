"""Builds one Scenario from one flights.csv row (A-3, A-4, A-5).

Real:        focal flight (schedule, delays, tail), delayed arrivals at the destination,
             the tail's next leg when it is in the file.
Organiser:   airport runways/capacity/turnaround/spare gates, wake table, fuel and crew rules.
Synthetic:   everything else, drawn from a seeded RNG and tagged in `scenario.provenance`.
             Synthetic flights have IDs starting with "SYN-".
Assumptions that are ours (not the workbook's) are listed in scenarios.workbook.OUR_ASSUMPTIONS.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from contracts import (
    ATCPrivate, Connection, FocalFlight, Gate, GateBooking, GroundPrivate, NextLeg, PilotPrivate,
    Provenance as P, PublicInfo, RouteOption, Scenario, SequencedArrival, SizeClass, WakeCategory,
)
from scenarios.flights import FlightIndex, aircraft_class
from scenarios.workbook import Workbook

TAXI_OUT_MIN = 14.0             # median TAXI_OUT in flights.csv
TAXI_TOTAL_MIN = 20.0           # median taxi-out + taxi-in, removed from SCHEDULED_TIME
DECISION_LEAD_MIN = 30.0
WINDOW_BEFORE_MIN, WINDOW_AFTER_MIN = 90.0, 180.0
MAX_HOLDING_MIN = 30.0
MAX_OVERTIME_MIN = 60.0
MIN_CONNECT_MIN = 35.0
SHIFT_STARTS = (6 * 60, 14 * 60, 22 * 60)   # three 8 h ramp shifts per day
CREW_SIZE = {SizeClass.REGIONAL: 4, SizeClass.NARROWBODY: 6, SizeClass.WIDEBODY: 10}
CONNECTION_BANKS = {"Large hub": 3, "Medium hub": 2, "Small hub": 1}
DEMAND_SHARE = {"Large hub": (0.75, 0.95), "Medium hub": (0.65, 0.9), "Small hub": (0.5, 0.8), "Non-hub": (0.3, 0.6)}
HEAVY_SHARE = {"Large hub": 0.12, "Medium hub": 0.06, "Small hub": 0.02, "Non-hub": 0.0}
SMALL_SHARE = 0.03
SLOT_RELEASE_SHARE = 0.06       # GDP slots released by cancellations/swaps -> holes
GATE_SIZES = (SizeClass.NARROWBODY, SizeClass.WIDEBODY, SizeClass.REGIONAL)
GATE_SIZE_P = (0.6, 0.2, 0.2)   # spare gate sizes


def weather_cut(weather_delay: float) -> float:
    return min(0.5, 0.15 + weather_delay / 400.0) if weather_delay > 15 else 0.0


def build_scenario(row: pd.Series, idx: FlightIndex, wb: Workbook, seed: int,
                   scenario_id: str | None = None) -> Scenario:
    rng = np.random.default_rng(seed)
    dest, airline = row.DESTINATION_AIRPORT, row.AIRLINE
    airport = wb.airports[dest]
    fc = wb.fuel_crew
    day0 = int(row.day) * 1440
    size, wake = aircraft_class(airline, row.DISTANCE)
    is_weather = bool(row.WEATHER_DELAY > 15)
    late_min = float(row.LATE_AIRCRAFT_DELAY) if row.LATE_AIRCRAFT_DELAY > 0 else 0.0
    prov: dict[str, P] = {"public.focal": P.REAL, "public.focal.wake_category": P.SYNTHETIC,
                          "public.focal.size_class": P.SYNTHETIC, "public.focal.taxi_out_min": P.REAL_DERIVED}

    # ---------------------------------------------------------------- focal flight
    sched_dep = float(row.sched_dep_abs_dest - day0)
    sched_arr = float(row.sched_arr_abs - day0)
    focal = FocalFlight(
        flight_id=row.flight_id, airline=airline, flight_number=int(row.FLIGHT_NUMBER),
        tail_number=row.TAIL_NUMBER, origin=row.ORIGIN_AIRPORT, destination=dest, date=row.date,
        sched_departure_min=sched_dep, sched_arrival_min=sched_arr, taxi_out_min=TAXI_OUT_MIN,
        wake_category=wake, size_class=size,
        recorded_arrival_delay_min=float(row.ARRIVAL_DELAY),
        recorded_weather_delay_min=float(row.WEATHER_DELAY),
        recorded_late_aircraft_delay_min=float(row.LATE_AIRCRAFT_DELAY),
    )
    decision = sched_dep - DECISION_LEAD_MIN
    ready = sched_dep + late_min if late_min else None
    prov["public.ready_min"] = P.REAL_DERIVED
    planned_air = max(float(row.SCHEDULED_TIME) - TAXI_TOTAL_MIN, 0.5 * float(row.SCHEDULED_TIME))
    eta = max(decision, sched_dep, ready or 0.0) + TAXI_OUT_MIN + planned_air

    # ---------------------------------------------------------------- routes and fuel
    burn = (fc.holding_burn_wide_kg_h if size == SizeClass.WIDEBODY else fc.holding_burn_narrow_kg_h) / 60.0
    trip_fuel = planned_air * burn
    routes = [RouteOption(
        route_id="nominal", air_time_min=round(planned_air, 1), trip_fuel_kg=round(trip_fuel),
        through_weather=bool(is_weather and rng.random() < 0.2),
        turbulence_min=float(rng.integers(4, 16) if is_weather else rng.integers(0, 5)),
    )]
    if is_weather:
        routes.append(RouteOption(route_id="reroute", air_time_min=round(planned_air * 1.12, 1),
                                  trip_fuel_kg=round(trip_fuel * 1.12),
                                  turbulence_min=round(routes[0].turbulence_min * 0.2, 1)))
    prov["public.routes"] = P.SYNTHETIC

    # ---------------------------------------------------------------- arrival stream on our runway
    n_arr_rwy = max(1, airport.active_runways // 2)
    base_rate = airport.max_runway_ops_per_hour * 0.5 / n_arr_rwy
    reduced_rate = base_rate * (1.0 - weather_cut(float(row.WEATHER_DELAY)))
    spacing = 60.0 / reduced_rate
    w_start, w_end = eta - WINDOW_BEFORE_MIN, eta + WINDOW_AFTER_MIN
    grid = np.round(w_start + spacing * np.arange(int((w_end - w_start + 240) / spacing)), 2)
    taken: dict[int, SequencedArrival] = {}

    def first_free(t: float) -> int:
        k = int(np.searchsorted(grid, t - 1e-6))
        while k in taken:
            k += 1
        return k

    # Real delayed arrivals in the file, snapped to the grid at their actual landing time.
    arr = idx.arrivals_by_dest[dest]
    lo, hi = np.searchsorted(arr.landing_abs.values, [day0 + w_start, day0 + w_end])
    real = arr.iloc[lo:hi]
    real = real[(real.flight_id != row.flight_id) & (rng.random(len(real)) < 1.0 / n_arr_rwy)]
    for r in real.itertuples(index=False):
        k = first_free(r.landing_abs - day0)
        if k < len(grid):
            taken[k] = SequencedArrival(flight_id=r.flight_id, slot_min=float(grid[k]),
                                        wake_category=aircraft_class(r.AIRLINE, r.DISTANCE)[1])

    # Synthetic filler traffic up to the airport's demand level, plus the focal flight,
    # allocated by Ration-by-Schedule: scheduled order, never before the flight can arrive.
    lo_share, hi_share = DEMAND_SHARE.get(airport.size_class, (0.5, 0.8))
    demand = rng.poisson(base_rate * rng.uniform(lo_share, hi_share) * (w_end - w_start) / 60.0)
    n_fill = max(0, demand - len(real))
    fill_times = np.sort(rng.uniform(w_start, w_end, n_fill))
    heavy_p = HEAVY_SHARE.get(airport.size_class, 0.0)
    queue = [(t, f"SYN-{i:03d}", t) for i, t in enumerate(fill_times)]
    queue.append((sched_arr - 6.0, "FOCAL", eta))
    filler_slots = []
    rbs_k = None
    for _, fid, earliest in sorted(queue):
        k = first_free(earliest)
        if k >= len(grid):
            continue
        if fid == "FOCAL":
            rbs_k = k
            taken[k] = None
            continue
        u = rng.random()
        wc = WakeCategory.HEAVY if u < heavy_p else WakeCategory.SMALL if u < heavy_p + SMALL_SHARE else WakeCategory.LARGE
        taken[k] = SequencedArrival(flight_id=fid, slot_min=float(grid[k]), wake_category=wc)
        filler_slots.append(k)
    for k in rng.choice(filler_slots, size=int(len(filler_slots) * SLOT_RELEASE_SHARE), replace=False):
        del taken[int(k)]

    rbs_slot = float(grid[rbs_k])
    sequence = sorted((a for a in taken.values() if a is not None), key=lambda a: a.slot_min)
    free_slots = [float(t) for k, t in enumerate(grid) if k not in taken and eta - 1e-6 <= t <= w_end]
    prov.update({"atc.arrival_sequence": P.SYNTHETIC if n_fill else P.REAL_DERIVED,
                 "atc.base_aar_per_hour": P.ORGANISER, "atc.reduced_aar_per_hour": P.SYNTHETIC,
                 "public.available_slots_min": P.SYNTHETIC, "public.rbs_slot_min": P.SYNTHETIC})

    # ---------------------------------------------------------------- gates
    taxi_in = float(np.clip(row.TAXI_IN, 3, 15))
    planned = Gate(gate_id=f"A{rng.integers(1, 40)}", zone="A", size=size, airline=airline, taxi_in_min=taxi_in)
    gates = [planned]
    for i in range(2):  # neighbouring gates of the same airline, busy until around our arrival
        gates.append(Gate(gate_id=f"A{40 + i}", zone="A", size=size, airline=airline, taxi_in_min=taxi_in))
    for i, zone in enumerate("BCDE"[:airport.spare_gates]):
        gsize = GATE_SIZES[rng.choice(len(GATE_SIZES), p=GATE_SIZE_P)]
        gates.append(Gate(gate_id=f"{zone}{rng.integers(1, 30)}", zone=zone, size=gsize,
                          airline=str(rng.choice([airline, "COMMON"])),
                          taxi_in_min=taxi_in + float(rng.integers(1, 8))))
    prov["public.gates"] = P.SYNTHETIC

    def booking(gate_id: str, start: float, length: float, n: int) -> GateBooking:
        return GateBooking(gate_id=gate_id, flight_id=f"SYN-GATE-{n}", start_min=round(start, 1),
                           end_min=round(start + length, 1))

    bookings = []
    if rng.random() < 0.6:   # our late arrival lost its planned gate to another flight for a while
        bookings.append(booking(planned.gate_id, sched_arr + rng.uniform(15, 45), rng.uniform(45, 90), 0))
    for i, g in enumerate(gates[1:3], start=1):
        end = eta + rng.uniform(-20, 60)
        bookings.append(booking(g.gate_id, w_start, end - w_start, 10 * i))
        bookings.append(booking(g.gate_id, end + rng.uniform(30, 90), 60.0, 10 * i + 1))
    for i, g in enumerate(gates[3:], start=5):
        bookings.append(booking(g.gate_id, eta + rng.uniform(20, 150), rng.uniform(40, 90), 10 * i))
    prov["ground.gate_bookings"] = P.SYNTHETIC

    # ---------------------------------------------------------------- next leg (real when in the file)
    legs = idx.legs_by_tail.get(row.TAIL_NUMBER)
    nxt = None
    if legs is not None:
        later = legs[(legs.ORIGIN_AIRPORT == dest) & (legs.sched_dep_abs_origin > row.sched_arr_abs)
                     & (legs.sched_dep_abs_origin < row.sched_arr_abs + 720)]
        if len(later):
            n = later.iloc[0]
            nxt = NextLeg(flight_id=n.flight_id, sched_departure_min=float(n.sched_dep_abs_origin - day0))
            prov["ground.next_leg"] = P.REAL_DERIVED
    if nxt is None:
        nxt = NextLeg(flight_id="SYN-NEXT",
                      sched_departure_min=round(sched_arr + airport.min_turnaround_min + rng.uniform(10, 60), 1))
        prov["ground.next_leg"] = P.SYNTHETIC

    shift_end = next(d * 1440 + s + 480 for d in (-1, 0, 1) for s in SHIFT_STARTS if d * 1440 + s + 480 > sched_arr)
    ground = GroundPrivate(
        planned_gate_id=planned.gate_id, gate_bookings=bookings,
        min_turnaround_min=airport.min_turnaround_min, next_leg=nxt,
        ramp_crew_size=CREW_SIZE[size], crew_shift_end_min=float(shift_end), max_overtime_min=MAX_OVERTIME_MIN,
    )
    prov.update({"ground.min_turnaround_min": P.ORGANISER, "ground.crew_shift_end_min": P.ORGANISER,
                 "ground.max_overtime_min": P.SYNTHETIC, "ground.ramp_crew_size": P.SYNTHETIC})

    # ---------------------------------------------------------------- pilot / airline
    first_dep = sched_dep
    if legs is not None:
        same_day = legs[(legs.day == row.day) & (legs.sched_dep_abs_origin < row.sched_dep_abs_origin)]
        if len(same_day):
            first_dep = min(first_dep, float(same_day.sched_dep_abs_origin.min() - day0))
    report = first_dep - 60.0 - rng.uniform(0, 240)   # earlier undelayed legs are not in the file
    # Crews change aircraft, so the tail's first leg is not the crew's. Keep the schedule itself legal,
    # with a seeded margin, so that only delays can push the crew out of duty.
    duty_end = max(report + fc.crew_max_duty_h * 60.0, sched_arr + rng.uniform(30, 240))
    banks = CONNECTION_BANKS.get(airport.size_class, 0)
    pax_scale = 0.5 if size == SizeClass.REGIONAL else 1.0
    connections = [
        Connection(flight_id=f"SYN-CNX-{i}", departure_min=round(sched_arr + rng.uniform(40, 150), 1),
                   pax=max(1, int(rng.integers(4, 31) * pax_scale)), min_connect_min=MIN_CONNECT_MIN)
        for i in range(banks)
    ]
    pilot = PilotPrivate(
        fuel_on_board_kg=round(trip_fuel * (1 + fc.contingency_fraction)
                               + (fc.spare_holding_on_arrival_min + fc.final_reserve_min) * burn),
        holding_burn_kg_per_min=round(burn, 2), alternate_airport="none", alternate_fuel_kg=0.0,
        final_reserve_min=fc.final_reserve_min,
        crew_duty_end_min=round(duty_end, 1), connections=connections,
    )
    prov.update({"pilot.fuel_on_board_kg": P.ORGANISER, "pilot.holding_burn_kg_per_min": P.ORGANISER,
                 "pilot.final_reserve_min": P.ORGANISER, "pilot.crew_duty_end_min": P.SYNTHETIC,
                 "pilot.connections": P.SYNTHETIC})

    # ---------------------------------------------------------------- ATC
    closed = [str(rng.choice(list("BCDE"[:airport.spare_gates])))] if is_weather and rng.random() < 0.15 else []
    atc = ATCPrivate(base_aar_per_hour=round(base_rate, 2), reduced_aar_per_hour=round(reduced_rate, 2),
                     arrival_sequence=sequence, closed_taxiway_zones=closed, max_holding_min=MAX_HOLDING_MIN)
    prov.update({"atc.closed_taxiway_zones": P.SYNTHETIC, "atc.max_holding_min": P.SYNTHETIC})

    cause = []
    if is_weather:
        cause.append(f"weather at {dest}: arrival rate per runway cut from {base_rate:.0f} to {reduced_rate:.0f}/h, "
                     "Ground Delay Program in effect")
    if late_min:
        cause.append(f"inbound aircraft {row.TAIL_NUMBER} is {late_min:.0f} min late")
    public = PublicInfo(
        decision_point="pre_departure", decision_time_min=decision, focal=focal, routes=routes, gates=gates,
        available_slots_min=free_slots, rbs_slot_min=rbs_slot, ready_min=ready,
        weather_summary=f"{airport.name} ({airport.size_class}). " + "; ".join(cause) + ".",
    )
    return Scenario(scenario_id=scenario_id or row.flight_id, track="A", seed=int(seed), public=public,
                    atc=atc, pilot=pilot, ground=ground, provenance=prov)
