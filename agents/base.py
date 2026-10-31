"""Agent interface and hard guards (C-4, C-5).

An Agent represents one organisation. It is built from `scenario.view(role)`, so it can only
ever see public data plus its own private data. On construction it evaluates every option
with workstream B's tools (own rules, own private cost).

Division of labour inside an agent:
- STRATEGY (subclass: scripted, LLM, misreporting) decides the move: which option to propose,
  accept or counter, whether to reveal more, what to say.
- CODE (this class) computes every number that leaves the agent: vetoes, rankings, regret
  scores, raw data at D3, rule evidence. A strategy cannot alter them.
- GUARD (this class) runs on every outgoing message: an agent can never PROPOSE, ACCEPT or
  COUNTER an option its own checker rejects, whatever the strategy (or the LLM) says.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from contracts import ROLES, Role, Scenario
from protocol.messages import AgentMessage, Claim, Disclosure, MediatorMessage, Preferences, Veto
from sim import check, generate_options, role_cost
from sim.params import DEFAULT_COSTS, CostParams

TOL_USD = 1.0      # "no worse than the fallback" tolerance
# Acceptance policy (team decision: bounded concession is the benchmark default).
#   rational    - never accept anything worse than the fallback
#   budget      - accept a loss vs the fallback up to max(CONCESSION_USD, CONCESSION_FRAC x fallback cost)
#   cooperative - accept any plan that passes own hard rules
ACCEPTANCE_MODES = ("rational", "budget", "cooperative")
CONCESSION_USD = 500.0
CONCESSION_FRAC = 0.10


@dataclass
class Draft:
    """A strategy's decision before the guard and the code-computed fields are applied."""
    type: str
    option_id: str | None = None
    acceptable: list[str] = field(default_factory=list)
    counter_kind: str | None = None
    claims: list[str] = field(default_factory=list)
    rationale: str = ""
    author: str = ""
    notes: list[str] = field(default_factory=list)   # audit notes carried into guard_notes


@dataclass
class Context:
    """What the agent knows about the negotiation so far (all of it from mediator messages)."""
    disclosure: Disclosure
    scenario_id: str
    turn: int = 1
    option_ids: list[str] = field(default_factory=list)
    feasible_ids: list[str] | None = None      # options nobody vetoed
    fallback_id: str | None = None
    proposed: list[str] = field(default_factory=list)
    relayed: list[dict] = field(default_factory=list)
    note: str = ""


class Agent:
    strategy = "base"

    def __init__(self, view: Scenario, role: Role, params: CostParams = DEFAULT_COSTS,
                 acceptance: str = "budget"):
        if acceptance not in ACCEPTANCE_MODES:
            raise ValueError(f"acceptance must be one of {ACCEPTANCE_MODES}")
        self.acceptance = acceptance
        others = [r for r in ROLES if r != role and getattr(view, r) is not None]
        if others:
            raise ValueError(f"{role} agent was given other organisations' private data: {others}")
        if getattr(view, role) is None:
            raise ValueError(f"{role} agent needs its own private data")
        self.role, self.view, self.params = role, view, params
        self.options = generate_options(view)
        self.by_id = {o.option_id: o for o in self.options}
        self.checks = {o.option_id: check(role, view, o) for o in self.options}
        self.costs = {o.option_id: role_cost(role, view, o, params) for o in self.options}
        self.own_feasible = [o.option_id for o in self.options if all(r.passed for r in self.checks[o.option_id])]
        self._feasible_set = set(self.own_feasible)
        self.ctx: Context | None = None
        self.guard_log: list[dict] = []          # every block/repair the guard made (C-5 metrics)

    # ------------------------------------------------------------------ code-computed facts
    def cost(self, oid: str) -> float:
        return self.costs[oid].total_usd

    def failed_rules(self, oid: str) -> list[str]:
        return [r.rule_id for r in self.checks[oid] if not r.passed]

    def is_safe(self, oid: str | None) -> bool:
        return oid in self._feasible_set

    def ranked(self, pool) -> list[str]:
        return sorted((o for o in pool if self.is_safe(o)), key=lambda o: (self.cost(o), o))

    def batna(self) -> float | None:
        f = self.ctx.fallback_id if self.ctx else None
        return self.cost(f) if f else None

    def allowed_loss(self) -> float:
        """How much worse than the fallback this agent will accept (USD)."""
        b = self.batna()
        if self.acceptance == "rational" or b is None:
            return TOL_USD
        if self.acceptance == "cooperative":
            return float("inf")
        return max(CONCESSION_USD, CONCESSION_FRAC * b)

    def max_acceptable_cost(self) -> float:
        return self.batna() + self.allowed_loss()

    def vetoes(self) -> list[Veto]:
        return [Veto(option_id=o.option_id, rule_ids=self.failed_rules(o.option_id))
                for o in self.options if not self.is_safe(o.option_id)]

    def true_regret(self) -> dict[str, float]:
        """0 = own cheapest acceptable option, 1 = own most expensive acceptable option."""
        costs = {o: self.cost(o) for o in self.own_feasible}
        if not costs:
            return {}
        lo, hi = min(costs.values()), max(costs.values())
        return {o: (0.0 if hi - lo < 1e-9 else round((c - lo) / (hi - lo), 4)) for o, c in costs.items()}

    def preferences(self, level: Disclosure) -> Preferences | None:
        """What this agent discloses at `level`. Overridden only by the misreporting agent (C-9)."""
        if level == "D0":
            return None
        if level == "D1":
            levels = sorted({round(self.cost(o), 2) for o in self.own_feasible})   # ties share a rank
            return Preferences(level="D1", ranks={o: levels.index(round(self.cost(o), 2)) for o in self.own_feasible})
        if level == "D2":
            return Preferences(level="D2", regret=self.true_regret())
        return Preferences(level="D3", private_data=getattr(self.view, self.role).model_dump(mode="json"))

    def attest(self, oid: str):
        """Own rule results for an option (used by the mediator's final safety gate)."""
        return self.checks[oid]

    # ------------------------------------------------------------------ protocol entry point
    def respond(self, msg: MediatorMessage) -> AgentMessage:
        if self.ctx is None:
            self.ctx = Context(disclosure=msg.disclosure, scenario_id=msg.scenario_id)
        c = self.ctx
        c.turn, c.note, c.relayed = msg.turn, msg.note, msg.relayed
        if msg.type == "BROADCAST":
            c.option_ids = msg.option_ids
        else:
            c.feasible_ids, c.fallback_id, c.proposed = msg.feasible_ids, msg.fallback_id, msg.option_ids
        if msg.turn == 1:
            draft = self.decide_turn1() if self.own_feasible else Draft(
                "ESCALATE", rationale=f"Every option fails my hard rules ({self._veto_summary()}).")
        elif msg.turn == 2:
            draft = self.decide_turn2()
        else:
            draft = self.decide_turn3()
        return self._finalise(draft)

    # strategy hooks -------------------------------------------------------------------------
    def decide_turn1(self) -> Draft:
        raise NotImplementedError

    def decide_turn2(self) -> Draft:
        raise NotImplementedError

    def decide_turn3(self) -> Draft:
        raise NotImplementedError

    # ------------------------------------------------------------------ guard
    def _block(self, what: str, notes: list[str], severity: str = "unsafe"):
        """severity "unsafe": a move that would break a rule or the protocol was stopped (safety metric);
        "cleanup": a harmless malformed field was dropped (reported separately)."""
        notes.append(what)
        self.guard_log.append({"turn": self.ctx.turn, "role": self.role, "blocked": what, "severity": severity})

    def _finalise(self, d: Draft) -> AgentMessage:
        c, notes = self.ctx, list(d.notes)
        typ, oid = d.type, d.option_id
        if typ in ("PROPOSE", "ACCEPT", "COUNTER"):
            if oid not in self.by_id:
                self._block(f"{typ} of unknown option {oid!r} blocked", notes)
                typ, oid = ("PROPOSE", self.ranked(self.own_feasible)[0]) if c.turn == 1 else ("REJECT", None)
            elif not self.is_safe(oid):
                self._block(f"{typ} of {oid} blocked: fails own rules {self.failed_rules(oid)}", notes)
                typ, oid = ("PROPOSE", self.ranked(self.own_feasible)[0]) if c.turn == 1 else ("REJECT", None)
        if typ == "ACCEPT" and c.turn >= 2 and oid not in c.proposed:
            self._block(f"ACCEPT of {oid} blocked: it was not proposed", notes)
            typ, oid = "REJECT", None
        if typ == "COUNTER" and c.feasible_ids is not None and oid not in c.feasible_ids:
            self._block(f"COUNTER with {oid} blocked: another organisation vetoed it", notes)
            typ, oid = "REJECT", None
        acceptable = []
        for a in (d.acceptable if typ == "ACCEPT" else []):   # the field only means something on an ACCEPT
            if a == oid:
                continue
            if not self.is_safe(a):
                self._block(f"'acceptable' entry {a} dropped: fails own rules {self.failed_rules(a)}", notes)
            elif a not in c.proposed:
                self._block(f"'acceptable' entry {a} dropped: it was not proposed", notes, "cleanup")
            else:
                acceptable.append(a)
        counter_kind = d.counter_kind if typ == "COUNTER" else None
        if typ == "COUNTER" and counter_kind not in ("concede", "reveal", "variant"):
            counter_kind = "variant"
        rationale = d.rationale
        if typ != d.type:     # the guard replaced the move: say so, keep the original text for the audit trail
            rationale = f"[GUARD replaced {d.type} with {typ}] Original rationale: {d.rationale}"
        prefs = None
        if c.turn == 1:
            prefs = self.preferences(c.disclosure)
        elif counter_kind == "reveal":
            prefs = self.preferences("D2")          # reveal = disclose scores beyond the episode level
        return AgentMessage(
            scenario_id=c.scenario_id, turn=c.turn, sender=self.role, type=typ, option_id=oid,
            acceptable=acceptable, vetoes=self.vetoes() if c.turn == 1 else [], preferences=prefs,
            counter_kind=counter_kind, claims=[Claim(kind=k) for k in d.claims if k == "min_fuel"],
            evidence=self.checks[oid] if oid else [], rationale=rationale[:600],
            author=d.author or self.strategy, guard_notes=notes,
        )

    def _veto_summary(self) -> str:
        counts: dict[str, int] = {}
        for v in self.vetoes():
            for r in v.rule_ids:
                counts[r] = counts.get(r, 0) + 1
        return ", ".join(f"{r} x{n}" for r, n in sorted(counts.items())) or "none"

    def explain(self, oid: str) -> str:
        comps = {k: v for k, v in self.costs[oid].components_usd.items() if v}
        top = ", ".join(f"{k} ${v:,.0f}" for k, v in sorted(comps.items(), key=lambda kv: -kv[1])[:3])
        return f"${self.cost(oid):,.0f}" + (f" ({top})" if top else "")
