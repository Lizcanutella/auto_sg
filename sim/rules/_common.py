from __future__ import annotations

from contracts import Role, RuleResult


def rule(role: Role, rule_id: str, passed: bool, value: float | None, limit: float | None,
         unit: str, source: str, detail: str = "") -> RuleResult:
    return RuleResult(rule_id=rule_id, role=role, passed=bool(passed), value=value, limit=limit,
                      unit=unit, source=source, detail=detail)


def not_applicable(role: Role, rule_id: str, why: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, role=role, passed=True, source="n/a", detail=f"not applicable: {why}")
