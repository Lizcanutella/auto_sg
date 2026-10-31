"""Hard-constraint checks (B-2). Each organisation's checker needs only its own view."""
from __future__ import annotations

from contracts import ROLES, Option, Role, RuleResult, Scenario, Timeline
from sim.rules import atc, ground, pilot
from sim.simulate import compute_timeline

CHECKERS = {"atc": atc.check, "pilot": pilot.check, "ground": ground.check}


def check(role: Role, view: Scenario, option: Option, tl: Timeline | None = None) -> list[RuleResult]:
    return CHECKERS[role](view, option, tl)


def check_all(scenario: Scenario, option: Option) -> list[RuleResult]:
    """Run every checker whose private data is present in `scenario`."""
    tl = compute_timeline(scenario.public, option)
    return [r for role in ROLES if getattr(scenario, role) is not None for r in check(role, scenario, option, tl)]


def violations(results: list[RuleResult]) -> list[RuleResult]:
    return [r for r in results if not r.passed]
