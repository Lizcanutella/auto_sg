"""Builds the hand-made fixture scenarios (task S-3).

These are SYNTHETIC stand-ins shaped like a qualifying DOT row (ORD -> ATL, weather delay),
used until workstream A produces real scenarios. Every field is tagged synthetic.

  episode_001  pre-departure, ATL arrival rate cut 40 -> 30/h by thunderstorms. Designed so that:
               - at the RBS slot (19:18) only the far common-use gate D3 is free, so today's process
                 parks there and misses connections. ATC prefers this (its slot gets used);
               - a cancellation hole at 19:06 + gate B7 is better for the airline and the ground handler,
                 so the agents have a real trade-off to negotiate;
               - an earlier hole (18:52) sits right behind a heavy (wake veto: the "tempting unsafe" option);
               - airborne holding beyond ~23 min breaks the fuel rule, so delay must be taken on the ground;
               - a gate behind a closed taxiway (T5) and a crew duty limit cut off the latest options.
  episode_002  same flight, already airborne at 18:20 with little fuel: diverting is the only safe plan.
  episode_003  track B: crew duty ends before any possible block-in, so every option fails -> escalate.

Run:  python -m fixtures.build_fixtures
"""
from __future__ import annotations

from pathlib import Path

from contracts import (
    ATCPrivate, Connection, FocalFlight, Gate, GateBooking, GroundPrivate, NextLeg, PilotPrivate,
    Provenance, PublicInfo, RouteOption, Scenario, SequencedArrival, SizeClass, WakeCategory,
)

OUT = Path(__file__).parent
W = WakeCategory


def hm(h: int, m: int) -> float:
    return float(h * 60 + m)


FREE_SLOTS = [hm(18, 52), hm(19, 6), hm(19, 18), hm(19, 30), hm(19, 38), hm(19, 52), hm(20, 6), hm(20, 24)]
RBS_SLOT = hm(19, 18)
NON_LARGE = {hm(18, 30): W.HEAVY, hm(18, 50): W.HEAVY, hm(19, 10): W.B757, hm(19, 16): W.B757,
             hm(19, 36): W.HEAVY, hm(19, 46): W.HEAVY, hm(20, 0): W.SMALL, hm(20, 16): W.B757}


def arrival_sequence() -> list[SequencedArrival]:
    """Other arrivals on a 2-minute grid (30/h) from 18:20 to 20:40, minus the free slots."""
    seq = []
    t = hm(18, 20)
    while t <= hm(20, 40):
        if t not in FREE_SLOTS:
            seq.append(SequencedArrival(flight_id=f"ARR{int(t)}", slot_min=t,
                                        wake_category=NON_LARGE.get(t, W.LARGE)))
        t += 2.0
    return seq


def episode_001() -> Scenario:
    focal = FocalFlight(
        flight_id="DL1846-2015-07-14", airline="DL", flight_number=1846, tail_number="N000FX",
        origin="ORD", destination="ATL", date="2015-07-14",
        sched_departure_min=hm(17, 5), sched_arrival_min=hm(18, 55), taxi_out_min=18.0,
        wake_category=W.LARGE, size_class=SizeClass.NARROWBODY,
        recorded_arrival_delay_min=62.0, recorded_weather_delay_min=47.0,
    )
    public = PublicInfo(
        decision_point="pre_departure", decision_time_min=hm(16, 40), focal=focal,
        routes=[
            RouteOption(route_id="nominal", air_time_min=82.0, trip_fuel_kg=3300.0, turbulence_min=12.0),
            RouteOption(route_id="reroute_west", air_time_min=96.0, trip_fuel_kg=3850.0, turbulence_min=2.0),
        ],
        gates=[
            Gate(gate_id="A12", zone="A", size=SizeClass.NARROWBODY, airline="DL", taxi_in_min=9.0),
            Gate(gate_id="A14", zone="A", size=SizeClass.NARROWBODY, airline="DL", taxi_in_min=9.0),
            Gate(gate_id="B7", zone="B", size=SizeClass.NARROWBODY, airline="DL", taxi_in_min=11.0),
            Gate(gate_id="C40", zone="C", size=SizeClass.REGIONAL, airline="COMMON", taxi_in_min=13.0),
            Gate(gate_id="D3", zone="D", size=SizeClass.NARROWBODY, airline="COMMON", taxi_in_min=14.0),
            Gate(gate_id="T5", zone="T", size=SizeClass.WIDEBODY, airline="DL", taxi_in_min=6.0),
        ],
        available_slots_min=FREE_SLOTS, rbs_slot_min=RBS_SLOT,
        weather_summary=("Thunderstorms at ATL 18:30-20:00 local. Arrival rate cut from 40 to 30 per hour; "
                         "Ground Delay Program in effect. Moderate turbulence on the direct route over Tennessee."),
    )
    atc = ATCPrivate(base_aar_per_hour=40.0, reduced_aar_per_hour=30.0, arrival_sequence=arrival_sequence(),
                     closed_taxiway_zones=["T"], max_holding_min=20.0)
    pilot = PilotPrivate(
        fuel_on_board_kg=6640.0, holding_burn_kg_per_min=38.0, alternate_airport="CHA",
        alternate_fuel_kg=1300.0, final_reserve_min=30.0, crew_duty_end_min=hm(20, 35),
        connections=[
            Connection(flight_id="DL412-JFK", departure_min=hm(19, 30), pax=9, min_connect_min=35.0),
            Connection(flight_id="DL1500-MIA", departure_min=hm(19, 50), pax=14, min_connect_min=35.0),
            Connection(flight_id="DL880-LAX", departure_min=hm(20, 15), pax=22, min_connect_min=40.0),
        ],
    )
    ground = GroundPrivate(
        planned_gate_id="A12",
        gate_bookings=[
            GateBooking(gate_id="A12", flight_id="DL2001", start_min=hm(18, 10), end_min=hm(19, 45)),
            GateBooking(gate_id="A14", flight_id="DL733", start_min=hm(19, 10), end_min=hm(20, 15)),
            GateBooking(gate_id="B7", flight_id="DL95", start_min=hm(20, 5), end_min=hm(21, 0)),
            GateBooking(gate_id="D3", flight_id="F91201", start_min=hm(20, 20), end_min=hm(21, 0)),
        ],
        min_turnaround_min=40.0, next_leg=NextLeg(flight_id="DL2210-MCO", sched_departure_min=hm(19, 40)),
        ramp_crew_size=6, crew_shift_end_min=hm(20, 0), max_overtime_min=45.0,
    )
    return Scenario(scenario_id="episode_001", track="A", seed=1, public=public, atc=atc, pilot=pilot,
                    ground=ground, provenance={"*": Provenance.SYNTHETIC})


def episode_002() -> Scenario:
    base = episode_001()
    public = base.public.model_copy(update={
        "decision_point": "airborne", "decision_time_min": hm(18, 20),
        "routes": [
            RouteOption(route_id="nominal", air_time_min=25.0, trip_fuel_kg=1000.0, turbulence_min=3.0),
            RouteOption(route_id="divert_CHA", air_time_min=30.0, trip_fuel_kg=1150.0,
                        diversion_airport="CHA"),
        ],
    })
    pilot = base.pilot.model_copy(update={"fuel_on_board_kg": 3900.0})
    return base.model_copy(update={"scenario_id": "episode_002", "seed": 2, "public": public, "pilot": pilot})


def episode_003() -> Scenario:
    base = episode_001()
    pilot = base.pilot.model_copy(update={"crew_duty_end_min": hm(19, 0)})
    return base.model_copy(update={"scenario_id": "episode_003", "track": "B", "seed": 3, "pilot": pilot})


FIXTURES = {"episode_001": episode_001, "episode_002": episode_002, "episode_003": episode_003}


def load(name: str) -> Scenario:
    return Scenario.model_validate_json((OUT / f"{name}.json").read_text())


if __name__ == "__main__":
    for name, build in FIXTURES.items():
        (OUT / f"{name}.json").write_text(build().model_dump_json(indent=2))
        print(f"wrote {OUT / name}.json")
