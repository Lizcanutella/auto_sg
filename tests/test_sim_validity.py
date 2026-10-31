import pandas as pd
import pytest

from bench.sim_validity import FILE_THRESHOLD_MIN, implied_turnaround, pairs, score
from scenarios.flights import FLIGHTS, flight_index

pytestmark = pytest.mark.skipif(not FLIGHTS.exists(), reason="organiser data not present")


@pytest.fixture(scope="module")
def p():
    return pairs()


def test_pairing_matches_the_scenario_builders_next_leg(p):
    """Same rule as scenarios/build.py: first same-tail leg leaving our destination within 12 h."""
    idx = flight_index()
    for _, r in p.sample(25, random_state=0).iterrows():
        legs = idx.legs_by_tail[r.TAIL_NUMBER]
        later = legs[(legs.ORIGIN_AIRPORT == r.DESTINATION_AIRPORT) & (legs.sched_dep_abs_origin > r.sched_arr_abs)
                     & (legs.sched_dep_abs_origin < r.sched_arr_abs + 720)]
        assert later.iloc[0].flight_id == r.next_flight_id


def test_prediction_is_the_simulators_formula(p):
    r = p.iloc[:200]
    expected = (r.sched_arr_abs + r.ARRIVAL_DELAY + r.min_turnaround_min - r.next_sched_dep_abs).clip(lower=0)
    pd.testing.assert_series_equal(r.predicted_min, expected, check_names=False)
    assert (p.predicted_min >= 0).all()


def test_implied_turnaround_closes_the_loop(p):
    r = p[p.predicted_min >= FILE_THRESHOLD_MIN].iloc[:50]
    # with the implied turnaround in place of the workbook minimum, the model reproduces the record exactly
    pred = r.sched_arr_abs + r.ARRIVAL_DELAY + implied_turnaround(r) - r.next_sched_dep_abs
    pd.testing.assert_series_equal(pred, r.next_late_aircraft_delay.astype(float), check_names=False)


def test_score_basics():
    s = score(pd.Series([10.0, 20.0, 40.0]), pd.Series([10.0, 30.0, 30.0]))
    assert s["N"] == 3 and s["MAE"] == pytest.approx(20 / 3) and s["bias"] == 0.0
    assert s["within_15"] == 1.0
