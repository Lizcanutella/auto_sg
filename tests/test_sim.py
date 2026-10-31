import pytest

from baselines import best_possible, fcfs_rbs, siloed
from contracts import Gate, Option, SizeClass, WakeCategory
from fixtures.build_fixtures import FIXTURES, episode_001, load
from sim import check, check_all, evaluate, evaluate_all, generate_options, option_by_id, role_cost
from sim.params import CostParams


@pytest.fixture
def ep1():
    return load("episode_001")


def opt(scenario, option_id):
    return option_by_id(generate_options(scenario), option_id)


def result(scenario, option, rule_id):
    return next(r for r in check_all(scenario, option) if r.rule_id == rule_id)


def with_public(scenario, **update):
    return scenario.model_copy(update={"public": scenario.public.model_copy(update=update)})


# ------------------------------------------------------------------ fixtures & options

@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_json_matches_builder(name):
    assert load(name) == FIXTURES[name]()


def test_options_are_deterministic_unique_and_view_independent(ep1):
    ids = [o.option_id for o in generate_options(ep1)]
    assert len(ids) == len(set(ids)) == 140
    assert ids == [o.option_id for o in generate_options(episode_001())]
    for role in ("atc", "pilot", "ground"):
        assert [o.option_id for o in generate_options(ep1.view(role))] == ids


def test_options_skip_publicly_incompatible_gates(ep1):
    assert not any(o.gate_id == "C40" for o in generate_options(ep1))  # regional gate, narrowbody aircraft


def test_slot_before_earliest_landing_is_rejected(ep1):
    bad = Option(option_id="x", route_id="nominal", slot_min=1100.0, absorption="ground", gate_id="B7")
    with pytest.raises(ValueError, match="before earliest landing"):
        evaluate(ep1, bad)


def test_ground_delay_impossible_when_airborne():
    ep2 = load("episode_002")
    bad = Option(option_id="x", route_id="nominal", slot_min=1146.0, absorption="ground", gate_id="B7")
    with pytest.raises(ValueError, match="airborne"):
        evaluate(ep2, bad)


# ------------------------------------------------------------------ views

def test_view_hides_other_organisations(ep1):
    v = ep1.view("pilot")
    assert v.pilot is not None and v.atc is None and v.ground is None


def test_each_role_can_check_and_cost_with_only_its_own_view(ep1):
    o = opt(ep1, "nominal@19:06/ground/B7")
    for role in ("atc", "pilot", "ground"):
        v = ep1.view(role)
        assert check(role, v, o) == check(role, ep1, o)
        assert role_cost(role, v, o) == role_cost(role, ep1, o)


def test_role_cannot_use_another_roles_data(ep1):
    o = opt(ep1, "nominal@19:06/ground/B7")
    with pytest.raises(ValueError, match="not in this view"):
        check("atc", ep1.view("pilot"), o)


# ------------------------------------------------------------------ rules: pass and fail per rule

GOOD = "nominal@19:06/ground/B7"


@pytest.mark.parametrize("rule_id", [
    "ATC-SLOT", "ATC-WAKE-LEAD", "ATC-WAKE-FOLLOW", "ATC-CAP", "ATC-TWY", "ATC-HOLD",
    "PILOT-FUEL", "PILOT-DUTY", "PILOT-WX", "GND-GATE-FREE", "GND-GATE-SIZE", "GND-GATE-AIRLINE", "GND-NOTICE",
    "GND-CREW",
])
def test_good_option_passes_every_rule(ep1, rule_id):
    assert result(ep1, opt(ep1, GOOD), rule_id).passed


def test_atc_slot_fails_off_the_slot_list(ep1):
    o = Option(option_id="x", route_id="nominal", slot_min=1148.0, absorption="ground", gate_id="B7")
    assert not result(ep1, o, "ATC-SLOT").passed


def test_atc_wake_lead_fails_right_behind_a_heavy(ep1):
    r = result(ep1, opt(ep1, "nominal@18:52/ground/B7"), "ATC-WAKE-LEAD")
    assert not r.passed and r.value == 2.0 and r.limit == pytest.approx(2.14, abs=0.01)


def test_atc_wake_follow_fails_when_focal_is_heavy(ep1):
    heavy = with_public(ep1, focal=ep1.public.focal.model_copy(update={"wake_category": WakeCategory.HEAVY}))
    assert not result(heavy, opt(heavy, "nominal@19:52/ground/A12"), "ATC-WAKE-FOLLOW").passed


def test_atc_capacity_fails_when_aar_drops_further(ep1):
    tight = ep1.model_copy(update={"atc": ep1.atc.model_copy(update={"reduced_aar_per_hour": 20.0})})
    assert not result(tight, opt(tight, GOOD), "ATC-CAP").passed


def test_atc_taxiway_closure(ep1):
    assert not result(ep1, opt(ep1, "nominal@19:06/ground/T5"), "ATC-TWY").passed


def test_atc_holding_stack_limit(ep1):
    assert not result(ep1, opt(ep1, "nominal@19:06/airborne/B7"), "ATC-HOLD").passed  # 21 min > 20


def test_pilot_fuel_fails_for_long_airborne_holding(ep1):
    assert result(ep1, opt(ep1, "nominal@19:18/ground/D3"), "PILOT-FUEL").passed
    r = result(ep1, opt(ep1, "nominal@19:18/airborne/D3"), "PILOT-FUEL")  # 33 min holding
    assert not r.passed and r.value < r.limit


def test_pilot_duty_limit(ep1):
    assert result(ep1, opt(ep1, "nominal@20:24/ground/A12"), "PILOT-DUTY").passed  # in-block 20:33
    assert not result(ep1, opt(ep1, "nominal@20:24/ground/D3"), "PILOT-DUTY").passed  # in-block 20:38


def test_pilot_weather(ep1):
    stormy = with_public(ep1, routes=[ep1.public.routes[0].model_copy(update={"through_weather": True}),
                                      *ep1.public.routes[1:]])
    assert not result(stormy, opt(stormy, GOOD), "PILOT-WX").passed


def test_ground_gate_conflict(ep1):
    r = result(ep1, opt(ep1, "nominal@19:06/ground/A12"), "GND-GATE-FREE")
    assert not r.passed and "DL2001" in r.detail


def test_ground_gate_size(ep1):
    o = Option(option_id="x", route_id="nominal", slot_min=1146.0, absorption="ground", gate_id="C40")
    assert not result(ep1, o, "GND-GATE-SIZE").passed


def test_ground_gate_airline(ep1):
    aa = Gate(gate_id="E1", zone="E", size=SizeClass.NARROWBODY, airline="AA", taxi_in_min=12.0)
    s = with_public(ep1, gates=[*ep1.public.gates, aa])
    o = Option(option_id="x", route_id="nominal", slot_min=1146.0, absorption="ground", gate_id="E1")
    assert not result(s, o, "GND-GATE-AIRLINE").passed


def test_ground_gate_change_needs_20_min_notice(ep1):
    late = with_public(ep1, decision_point="airborne", decision_time_min=1140.0,
                       routes=[ep1.public.routes[0].model_copy(update={"air_time_min": 5.0, "trip_fuel_kg": 200.0})])
    r = result(late, opt(late, "nominal@19:06/airborne/B7"), "GND-NOTICE")  # in-block 19:17, 17 min notice
    assert not r.passed and r.value == 17.0
    assert result(late, opt(late, "nominal@19:06/airborne/A12"), "GND-NOTICE").passed  # planned gate kept


def test_ground_crew_overtime_cap(ep1):
    long_turn = ep1.model_copy(update={"ground": ep1.ground.model_copy(update={"min_turnaround_min": 90.0})})
    r = result(long_turn, opt(long_turn, GOOD), "GND-CREW")   # in-block 19:17, ready 20:47, shift ends 20:00
    assert not r.passed and r.value == 47.0


def test_next_shift_takes_flights_arriving_after_shift_end(ep1):
    e = evaluate(ep1, opt(ep1, "nominal@20:24/ground/A12"))   # in-block 20:33, shift ended 20:00
    assert e.outcome.ground.overtime_min == 0.0


# ------------------------------------------------------------------ costs

def test_global_cost_is_weighted_sum_of_roles(ep1):
    e = evaluate(ep1, opt(ep1, GOOD))
    assert e.global_cost_usd == pytest.approx(sum(c.total_usd for c in e.costs.values()))
    p = CostParams(weight_pilot=2.0)
    e2 = evaluate(ep1, opt(ep1, GOOD), p)
    assert e2.global_cost_usd == pytest.approx(e.global_cost_usd + e.costs["pilot"].total_usd)


def test_ground_delay_is_cheaper_than_holding(ep1):
    ground = evaluate(ep1, opt(ep1, "reroute_west@19:06/ground/B7"))
    airborne = evaluate(ep1, opt(ep1, "reroute_west@19:06/airborne/B7"))
    assert ground.global_cost_usd < airborne.global_cost_usd


def test_agents_disagree_in_episode_001(ep1):
    """The fixture must give the agents something to negotiate: ATC prefers the RBS slot."""
    feasible = [e for e in evaluate_all(ep1) if e.feasible]
    best_for = {role: min(feasible, key=lambda e: (e.costs[role].total_usd, e.global_cost_usd)).option.option_id
                for role in ("atc", "pilot", "ground")}
    assert best_for["atc"] == "nominal@19:18/ground/D3"
    assert best_for["pilot"] == best_for["ground"] == GOOD


# ------------------------------------------------------------------ baselines

@pytest.mark.parametrize("name", FIXTURES)
def test_best_possible_never_worse_than_fcfs_and_always_feasible(name):
    s = load(name)
    fcfs, best = fcfs_rbs.plan(s), best_possible.plan(s)
    assert fcfs.status == best.status
    if best.status == "plan":
        assert best.chosen.feasible and fcfs.chosen.feasible
        assert best.chosen.global_cost_usd <= fcfs.chosen.global_cost_usd


@pytest.mark.parametrize("name", FIXTURES)
def test_siloed_is_always_safe_and_never_beats_best(name):
    s = load(name)
    sil, best = siloed.plan(s), best_possible.plan(s)
    assert sil.status == best.status
    if sil.status == "plan":
        assert sil.chosen.feasible and sil.chosen.global_cost_usd >= best.chosen.global_cost_usd


def test_siloed_holds_in_the_air_when_limits_allow(ep1):
    roomy = ep1.model_copy(update={
        "atc": ep1.atc.model_copy(update={"max_holding_min": 60.0}),
        "pilot": ep1.pilot.model_copy(update={"fuel_on_board_kg": 9000.0}),
    })
    sil, fcfs = siloed.plan(roomy), fcfs_rbs.plan(roomy)
    assert sil.chosen.option.option_id == "nominal@19:18/airborne/D3"
    assert fcfs.chosen.option.option_id == "nominal@19:18/ground/D3"
    assert sil.chosen.global_cost_usd > fcfs.chosen.global_cost_usd
    assert "phone calls" in sil.reason


def test_siloed_falls_back_to_ground_delay_after_a_call(ep1):
    r = siloed.plan(ep1)   # 33 min holding breaks fuel and the holding stack, so the call forces ground delay
    assert r.chosen.option.option_id == "nominal@19:18/ground/D3"


def test_episode_001_baselines(ep1):
    assert fcfs_rbs.plan(ep1).chosen.option.option_id == "nominal@19:18/ground/D3"   # keeps the RBS slot
    assert best_possible.plan(ep1).chosen.option.option_id == GOOD                   # uses the 19:06 hole


def test_episode_002_only_safe_plan_is_to_divert():
    assert best_possible.plan(load("episode_002")).chosen.option.option_id == "divert_CHA/divert"


def test_episode_003_escalates():
    r = fcfs_rbs.plan(load("episode_003"))
    assert r.status == "escalate" and r.chosen is None and r.n_feasible == 0
