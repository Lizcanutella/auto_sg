"""ATC hard constraints: slot validity, wake separation, capacity, taxiway closure, holding."""
from __future__ import annotations

from contracts import Option, RuleResult, Scenario, Timeline
from sim import params
from sim.rules._common import not_applicable, rule
from sim.simulate import EPS, atc_outcome, compute_timeline, get_gate

ROLE = "atc"
RULE_IDS = ("ATC-SLOT", "ATC-WAKE-LEAD", "ATC-WAKE-FOLLOW", "ATC-CAP", "ATC-TWY", "ATC-HOLD")


def check(view: Scenario, option: Option, tl: Timeline | None = None) -> list[RuleResult]:
    tl = tl or compute_timeline(view.public, option)
    o = atc_outcome(view, option, tl)
    atc = view.atc
    if tl.is_diversion:
        return [not_applicable(ROLE, r, "diversion: no destination slot") for r in RULE_IDS]

    public = view.public
    slot_ok = option.slot_min in public.available_slots_min or option.slot_min == public.rbs_slot_min
    cap = int(atc.reduced_aar_per_hour + EPS)
    zone = get_gate(public, option.gate_id).zone
    return [
        rule(ROLE, "ATC-SLOT", slot_ok, option.slot_min, None, "min", params.SLOT_SOURCE,
             "slot is on the published GDP slot list" if slot_ok else "slot is not a free published slot"),
        _wake("ATC-WAKE-LEAD", o.leader_gap_min, o.leader_required_min, "behind preceding arrival"),
        _wake("ATC-WAKE-FOLLOW", o.follower_gap_min, o.follower_required_min, "ahead of following arrival"),
        rule(ROLE, "ATC-CAP", o.arrivals_in_hour <= cap, o.arrivals_in_hour, cap, "arrivals/h",
             params.CAPACITY_SOURCE, "arrivals in the landing hour vs reduced AAR"),
        rule(ROLE, "ATC-TWY", zone not in atc.closed_taxiway_zones, None, None, "", params.TAXIWAY_SOURCE,
             f"gate zone {zone} is " + ("closed" if zone in atc.closed_taxiway_zones else "reachable")),
        rule(ROLE, "ATC-HOLD", o.holding_min <= atc.max_holding_min + EPS, o.holding_min,
             atc.max_holding_min, "min", params.HOLDING_SOURCE, "airborne holding vs stack limit"),
    ]


def _wake(rule_id: str, gap: float | None, required: float | None, where: str) -> RuleResult:
    if gap is None:
        return not_applicable(ROLE, rule_id, f"no aircraft {where}")
    return rule(ROLE, rule_id, gap >= required - EPS, round(gap, 2), round(required, 2), "min",
                params.WAKE_SOURCE, f"wake spacing {where}")
