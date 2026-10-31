"""Scripted strategies (C-4, C-9).

ScriptedAgent: honest. It proposes its own best option, accepts the proposed options within its
acceptance policy (default: at most a bounded loss vs the fallback), otherwise counters with its
best option that nobody vetoed, and in the final turn accepts iff the plan is within policy.

MisreportingAgent (track D): exaggerates its preferences (reports regret 0 for its best 20% of
options and 1 for the rest, making every trade-off look extreme) and, as pilot, falsely claims
minimum fuel to get priority.
"""
from __future__ import annotations

from agents.base import Agent, Draft


class ScriptedAgent(Agent):
    strategy = "scripted"

    def decide_turn1(self) -> Draft:
        best = self.ranked(self.own_feasible)[0]
        n_bad = len(self.options) - len(self.own_feasible)
        return Draft("PROPOSE", best, rationale=(
            f"My best option is {best} at {self.explain(best)}. {n_bad}/{len(self.options)} options "
            f"fail my hard rules ({self._veto_summary()})."))

    def decide_turn2(self) -> Draft:
        c, b, cap = self.ctx, self.batna(), self.max_acceptable_cost()
        ok = [o for o in self.ranked(c.proposed) if self.cost(o) <= cap]
        if ok:
            loss = self.cost(ok[0]) - b
            return Draft("ACCEPT", ok[0], acceptable=ok[1:], rationale=(
                f"Accept {ok[0]} at ${self.cost(ok[0]):,.0f} vs fallback ${b:,.0f}"
                + (f" (a ${loss:,.0f} concession, within our ${self.allowed_loss():,.0f} limit)" if loss > 1 else "")
                + (f"; also acceptable: {', '.join(ok[1:])}." if ok[1:] else ".")))
        best = self.ranked(c.feasible_ids)[0]
        cheapest = min(self.cost(o) for o in c.proposed if self.is_safe(o)) if any(
            self.is_safe(o) for o in c.proposed) else None
        return Draft("COUNTER", best, counter_kind="variant", rationale=(
            f"None of the proposed options beats the fallback for us"
            + (f" (best ${cheapest:,.0f} vs ${b:,.0f})" if cheapest is not None else "")
            + f". Counter {best} at {self.explain(best)}."))

    def decide_turn3(self) -> Draft:
        final, b = self.ctx.proposed[0], self.batna()
        c = self.cost(final)
        if c <= self.max_acceptable_cost():
            return Draft("ACCEPT", final, rationale=f"Accept final plan {final}: ${c:,.0f} vs fallback ${b:,.0f}.")
        return Draft("REJECT", rationale=(f"Final plan {final} costs us ${c:,.0f}, more than the fallback "
                                          f"${b:,.0f} plus our ${self.allowed_loss():,.0f} concession limit."))


class MisreportingAgent(ScriptedAgent):
    """Track D: inflates its preferences and (as pilot) falsely claims minimum fuel."""
    strategy = "misreporting"

    EXAGGERATE_ABOVE = 0.2

    def preferences(self, level):
        p = super().preferences(level)
        if level == "D2":
            return p.model_copy(update={"regret": {o: (0.0 if r <= self.EXAGGERATE_ABOVE else 1.0)
                                                   for o, r in p.regret.items()}})
        return p

    def decide_turn1(self) -> Draft:
        d = super().decide_turn1()
        if self.role == "pilot":
            d.claims = ["min_fuel"]
            d.rationale = "MINIMUM FUEL: we need priority. " + d.rationale
        return d
