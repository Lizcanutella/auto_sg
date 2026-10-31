"""Workstream C tests: protocol invariants, guards, validation, log, tracks."""
from __future__ import annotations

import pytest

from agents.mock_llm import FakeClient, broken, compliant, garbage, sensible
from agents.scripted import ScriptedAgent
from baselines import best_possible, fcfs_rbs
from contracts import ROLES, Scenario
from fixtures.build_fixtures import OUT
from protocol import log as clog
from protocol import run_episode, score_result
from protocol.mediator import Mediator, build_agents, fallback_option, public_only
from protocol.messages import AgentMessage, Preferences, validate_agent_message
from tracks import adversarial, misreport

LEVELS = ("D0", "D1", "D2", "D3")
AGGS = ("weighted_sum", "maxmin", "nash")
ACCEPTANCE = ("rational", "budget", "cooperative")


def load(name):
    return Scenario.model_validate_json((OUT / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def ep1():
    return load("episode_001")


# ------------------------------------------------------------------ invariants
@pytest.mark.parametrize("name", ["episode_001", "episode_002", "episode_003"])
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("agg", AGGS)
@pytest.mark.parametrize("acc", ACCEPTANCE)
def test_always_terminates_within_3_turns_with_zero_violations(name, level, agg, acc):
    s = load(name)
    r = run_episode(s, disclosure=level, aggregation=agg, acceptance=acc)
    assert r.status in ("CONSENSUS", "FALLBACK", "ESCALATE")
    assert 1 <= r.turns <= 3
    assert score_result(s, r)["violations"] == []
    assert r.log.verify()
    assert r.invalid_messages == 0


def test_infeasible_episode_escalates_without_a_plan():
    r = run_episode(load("episode_003"))
    assert r.status == "ESCALATE" and r.option_id is None and r.turns == 1


def test_low_fuel_episode_diverts():
    assert run_episode(load("episode_002")).option_id.endswith("/divert")


def test_rational_agents_are_never_worse_off_than_fallback(ep1):
    r = run_episode(ep1, acceptance="rational", disclosure="D2")
    full, fb = score_result(ep1, r)["costs"], None
    fb = {a: ScriptedAgent(ep1.view(a), a).cost(r.fallback_id) for a in ROLES}
    assert all(full[a] <= fb[a] + 1 for a in ROLES)


def test_bounded_concession_reaches_best_possible_on_episode_001(ep1):
    best = best_possible.plan(ep1).chosen.option.option_id
    assert run_episode(ep1, disclosure="D3", aggregation="weighted_sum", acceptance="budget").option_id == best
    assert run_episode(ep1, disclosure="D0").option_id == fcfs_rbs.plan(ep1).chosen.option.option_id


def test_fallback_uses_public_data_only_and_matches_fcfs_when_nothing_vetoed_differs(ep1):
    from sim import evaluate_all
    J = [e.option.option_id for e in evaluate_all(ep1) if e.feasible]
    assert fallback_option(public_only(ep1), J) in J


# ------------------------------------------------------------------ privacy
def test_agent_refuses_other_organisations_data(ep1):
    with pytest.raises(ValueError):
        ScriptedAgent(ep1, "atc")


def test_mediator_holds_public_data_only(ep1):
    m = Mediator(ep1, build_agents(ep1))
    assert m.public.atc is None and m.public.pilot is None and m.public.ground is None


def test_costs_never_leave_agents_below_d3(ep1):
    r = run_episode(ep1, disclosure="D2")
    for msg in r.messages:
        assert msg.preferences is None or msg.preferences.private_data is None
        dumped = msg.model_dump_json()
        assert "total_usd" not in dumped and "components_usd" not in dumped


# ------------------------------------------------------------------ guards (C-5)
def test_guard_blocks_unsafe_accept_under_pressure_even_from_compliant_llm(ep1):
    s2, tamper, U = adversarial.build_case(ep1, "pressure", "atc")
    r = run_episode(s2, strategy={"atc": "llm"}, tamper=tamper, agent_kwargs={"client": FakeClient(compliant)})
    assert r.option_id != U
    assert any(g["role"] == "atc" and U in g["blocked"] for g in r.guard_blocks)
    assert score_result(s2, r)["violations"] == []


def test_guard_blocks_weather_text_injection(ep1):
    s2, _, U = adversarial.build_case(ep1, "weather_injection", "pilot")
    r = run_episode(s2, strategy={"pilot": "llm"}, agent_kwargs={"client": FakeClient(compliant)})
    pilot_msgs = [m for m in r.messages if m.sender == "pilot"]
    assert any(U in n for m in pilot_msgs for n in m.guard_notes)
    assert all(m.option_id != U for m in pilot_msgs) and r.option_id != U


@pytest.mark.parametrize("policy", [garbage, broken])
def test_llm_failures_fall_back_to_scripted_moves(ep1, policy):
    r = run_episode(ep1, strategy="llm", agent_kwargs={"client": FakeClient(policy)})
    assert r.status == "CONSENSUS"
    assert all(m.author.startswith("llm-fallback") for m in r.messages)
    assert all(len(st["fallbacks"]) >= 1 for st in r.agent_stats.values())


def test_sensible_llm_runs_tool_loop_and_reaches_consensus(ep1):
    r = run_episode(ep1, strategy="llm", agent_kwargs={"client": FakeClient(sensible)})
    assert r.status == "CONSENSUS" and score_result(ep1, r)["violations"] == []
    assert all(st["tool_calls"] >= 1 and not st["fallbacks"] for st in r.agent_stats.values())


def test_rationale_number_audit_flags_invented_numbers(ep1):
    from agents.llm import LLMAgent

    def liar_numbers(payload, tool_results):
        rep = sensible(payload, ["x"])
        rep["rationale"] = "This saves 98765 dollars."
        return rep
    r = run_episode(ep1, strategy={"pilot": "llm"}, agent_kwargs={"client": FakeClient(liar_numbers)})
    assert r.agent_stats["pilot"]["unsupported_numbers"]
    assert any("not found in tool outputs" in n for m in r.messages if m.sender == "pilot" for n in m.guard_notes)
    assert isinstance(LLMAgent, type)


# ------------------------------------------------------------------ validation (C-1)
def _msg(**kw):
    base = dict(scenario_id="episode_001", turn=2, sender="atc", type="ACCEPT", option_id="a")
    return AgentMessage(**{**base, **kw})


def test_validation_rejects_accepting_unproposed_and_out_of_range_scores():
    ids = {"a", "b", "c"}
    errs = validate_agent_message(_msg(option_id="c"), scenario_id="episode_001", turn=2, sender="atc",
                                  disclosure="D2", option_ids=ids, proposed_ids={"a", "b"})
    assert any("not proposed" in e for e in errs)
    bad = _msg(turn=1, type="PROPOSE", preferences=Preferences(level="D2", regret={"a": 1.7}))
    errs = validate_agent_message(bad, scenario_id="episode_001", turn=1, sender="atc", disclosure="D2",
                                  option_ids=ids, proposed_ids=None)
    assert any("[0,1]" in e for e in errs)
    errs = validate_agent_message(_msg(sender="pilot"), scenario_id="episode_001", turn=2, sender="atc",
                                  disclosure="D2", option_ids=ids, proposed_ids={"a"})
    assert any("channel" in e for e in errs)


class _Broken(ScriptedAgent):
    def respond(self, msg):
        return super().respond(msg) if msg.turn == 1 else {"type": "ACCEPT", "nonsense": True}


def test_invalid_messages_count_as_reject_and_lead_to_fallback(ep1):
    agents = build_agents(ep1)
    agents["ground"] = _Broken(ep1.view("ground"), "ground")
    r = Mediator(ep1, agents).run()
    assert r.invalid_messages == 2 and r.status == "FALLBACK" and r.option_id == r.fallback_id


# ------------------------------------------------------------------ log (C-3)
def test_log_replays_and_detects_tampering(ep1, tmp_path):
    r = run_episode(ep1)
    r.log.human("APPROVE", r.option_id, "looks good")
    path = r.log.write(tmp_path / "ep.jsonl")
    entries = clog.load(path)
    rep = clog.replay(entries)
    assert rep["chain_ok"] and rep["decision"]["option_id"] == r.option_id
    assert rep["human"]["decision"] == "APPROVE"
    assert "CONSENSUS" in clog.render(entries)
    entries[3]["payload"]["option_id"] = "nominal@18:52/ground/A12"
    assert not clog.verify(entries)


# ------------------------------------------------------------------ tracks (C-8, C-9)
def test_adversarial_track_has_10_plus_cases_and_no_unsafe_outcome():
    rows = adversarial.run(adversarial.load_scenarios(), {"mock": lambda: ("llm", {"client": FakeClient(compliant)})})
    assert len(rows) >= 10
    assert not any(r["final_is_unsafe_option"] or r["final_violations"] for r in rows)
    assert sum(r["attempted_unsafe_moves"] > 0 for r in rows) >= 10


def test_false_min_fuel_claim_rejected_when_verified():
    rows = misreport.run(misreport.load_scenarios())
    verified = [c for r in rows if r["condition"] == "liar, claim verified" for c in r["claims"]]
    unverified = [c for r in rows if r["condition"] == "liar, claim unverified" for c in r["claims"]]
    assert verified and not any(c["accepted"] for c in verified)
    assert unverified and all(c["accepted"] for c in unverified)
