import pytest

from contracts import Provenance, WakeCategory as W
from scenarios.build import build_scenario
from scenarios.flights import FLIGHTS, flight_index
from scenarios.workbook import WORKBOOK, load_workbook
from sim import generate_options, params
from sim.params import DEFAULT_COSTS

pytestmark = pytest.mark.skipif(not (FLIGHTS.exists() and WORKBOOK.exists()), reason="organiser data not present")


@pytest.fixture(scope="module")
def wb():
    return load_workbook()


@pytest.fixture(scope="module")
def idx():
    return flight_index()


# ------------------------------------------------------------------ the sim must use the workbook's numbers

def test_wake_table_matches_workbook(wb):
    assert wb.wake_nm == params.WAKE_SEPARATION_NM
    assert wb.wake_default_nm == params.MIN_RADAR_SEPARATION_NM


def test_fuel_and_crew_rules_match_workbook(wb):
    fc = wb.fuel_crew
    assert (fc.final_reserve_min, fc.contingency_fraction, fc.spare_holding_on_arrival_min) == (30, 0.05, 45)
    assert (fc.holding_burn_narrow_kg_h, fc.holding_burn_wide_kg_h) == (2400, 6500)
    assert (fc.crew_max_duty_h, fc.ground_shift_h) == (13, 8)
    assert fc.gate_change_notice_min == params.GATE_CHANGE_NOTICE_MIN
    assert fc.overtime_multiplier == DEFAULT_COSTS.overtime_multiplier


def test_every_destination_has_airport_limits(wb, idx):
    assert set(idx.df.DESTINATION_AIRPORT) <= set(wb.airports)


# ------------------------------------------------------------------ loading

def test_overnight_arrival_lands_next_day(idx):
    """AA8 HNL-DFW 2015-01-01: departs 17:45 HST, arrives 05:10 CST next day, 445 min scheduled."""
    r = idx.df[(idx.df.flight_id == "AA8-2015-01-01")].iloc[0]
    day0 = r.day * 1440
    assert r.sched_arr_abs - day0 == 1440 + 5 * 60 + 10
    assert r.sched_dep_abs_dest - day0 == 21 * 60 + 45      # 17:45 HST on the Dallas clock


def test_every_row_qualifies(idx):
    assert ((idx.df.WEATHER_DELAY > 15) | (idx.df.LATE_AIRCRAFT_DELAY > 20)).all()


# ------------------------------------------------------------------ building

@pytest.fixture(scope="module")
def sample_rows(idx):
    df = idx.df
    return [df[df.is_weather].iloc[100], df[~df.is_weather].iloc[100], df[df.DESTINATION_AIRPORT == "ATL"].iloc[5]]


def test_build_is_deterministic(sample_rows, idx, wb):
    for row in sample_rows:
        assert build_scenario(row, idx, wb, seed=1) == build_scenario(row, idx, wb, seed=1)


def test_built_scenarios_are_consistent(sample_rows, idx, wb):
    for row in sample_rows:
        s = build_scenario(row, idx, wb, seed=1)
        p = s.public
        assert p.focal.flight_id == row.flight_id
        assert s.pilot.crew_duty_end_min > p.focal.sched_arrival_min          # schedule itself is legal
        assert s.ground.min_turnaround_min == wb.airports[row.DESTINATION_AIRPORT].min_turnaround_min
        if row.LATE_AIRCRAFT_DELAY > 0:
            assert p.ready_min == p.focal.sched_departure_min + row.LATE_AIRCRAFT_DELAY
        assert all(a.flight_id != row.flight_id for a in s.atc.arrival_sequence)
        assert len(generate_options(s)) > 0
        assert s.provenance["public.focal"] == Provenance.REAL
        assert s.provenance["pilot.fuel_on_board_kg"] == Provenance.ORGANISER


def test_weather_rows_cut_capacity_and_late_rows_do_not(sample_rows, idx, wb):
    weather, late = (build_scenario(r, idx, wb, seed=1) for r in sample_rows[:2])
    assert weather.atc.reduced_aar_per_hour < weather.atc.base_aar_per_hour
    assert late.atc.reduced_aar_per_hour == late.atc.base_aar_per_hour


def test_heavy_leader_wake_uses_workbook(wb):
    assert params.wake_separation_min(W.HEAVY, W.LARGE) == pytest.approx(5 / 140 * 60)
    assert params.wake_separation_min(W.LARGE, W.SMALL) == pytest.approx(4 / 140 * 60)
