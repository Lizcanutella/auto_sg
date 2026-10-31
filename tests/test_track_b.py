import pytest

from baselines import best_possible, fcfs_rbs, siloed
from fixtures.build_fixtures import load
from scenarios.track_b import KINDS, make_infeasible
from sim import check_all, generate_options


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_leaves_no_safe_plan_and_names_the_rule(kind):
    s = make_infeasible(load("episode_001"), kind)
    assert s.track == "B" and f"track_b:{kind}" in s.provenance
    for method in (best_possible, fcfs_rbs, siloed):
        assert method.plan(s).status == "escalate"
    expected = {"crew_timeout": "PILOT-DUTY", "fuel_short": "PILOT-FUEL",
                "no_gate": "GND-GATE-FREE", "airport_cut": "ATC-TWY"}[kind]
    assert all(any(r.rule_id == expected and not r.passed for r in check_all(s, o)) for o in generate_options(s))
