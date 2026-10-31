"""Mediator: deterministic 3-turn state machine (C-2).

Turn 1  BROADCAST option IDs (from public data) -> each agent: vetoes (rule IDs) + preferences at
        the episode's disclosure level + its first choice. Options anyone vetoed are dropped -> J.
        J empty, or an agent escalates -> ESCALATE (no plan, reasons logged).
        Fallback F = Ration-by-Schedule + first-fit gate within J (public data only).
Turn 2  PROPOSAL: top-k of J by the aggregation rule (with acceptance="rational", only options
        no agent rates worse than F). Agents ACCEPT (one, plus others also acceptable) /
        COUNTER (concede | reveal | variant) / REJECT.
        An option every agent accepted -> CONSENSUS now (fewer than 3 turns).
Turn 3  FINAL: one joint proposal from proposals + counters. Unanimous ACCEPT -> CONSENSUS,
        otherwise FALLBACK = F.
Always  Final safety gate: every agent's own checker re-attests the decided option. Invalid
        messages count as REJECT. The mediator never sees private data, except at D3 where
        agents send it on purpose, and never decides legality itself.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable, Literal

from baselines.fcfs_rbs import _dispatch_order
from contracts import ROLES, ATCPrivate, GroundPrivate, PilotPrivate, Role, Scenario
from protocol.log import ConsensusLog
from protocol.messages import (
    AgentMessage, Claim, Disclosure, MediatorMessage, parse_agent_message, validate_agent_message,
)
from sim import evaluate, generate_options, option_by_id, role_cost
from sim.params import DEFAULT_COSTS, CostParams
from sim.simulate import pilot_outcome

Aggregation = Literal["weighted_sum", "maxmin", "nash"]
Status = Literal["CONSENSUS", "FALLBACK", "ESCALATE"]
PRIVATE_MODELS = {"atc": ATCPrivate, "pilot": PilotPrivate, "ground": GroundPrivate}
MIN_FUEL_PRIORITY_WEIGHT = 3.0     # a verified minimum-fuel claim triples the pilot's weight
MIN_FUEL_MARGIN_MIN = 10.0         # genuine minimum fuel: < 10 min of holding fuel above the legal minimum
NASH_EPS = 1e-3


def public_only(s: Scenario) -> Scenario:
    return s.model_copy(update={r: None for r in ROLES})


def fallback_option(public: Scenario, feasible_ids: list[str]) -> str:
    """Today's process (RBS slot, then later slots, nominal route, ground delay first, first-fit
    gate by ID) restricted to options nobody vetoed. Uses public data only."""
    opts = {o.option_id: o for o in generate_options(public)}
    return min(feasible_ids, key=lambda oid: _dispatch_order(public, SimpleNamespace(option=opts[oid])))


class ClaimVerifier:
    """Independent check of verifiable claims (models an airline-to-ATC fuel data link / post-event
    flight-data audit). Holds only the pilot's view; the mediator itself never sees it.

    Minimum fuel = even the best plan that still lands at the destination leaves less than
    MIN_FUEL_MARGIN_MIN of holding fuel above the legal minimum (alternate + final reserve). If no
    destination landing exists, the best diversion is used."""

    def __init__(self, pilot_view: Scenario):
        self.view = pilot_view

    def margin_min(self) -> tuple[float, str]:
        burn = self.view.pilot.holding_burn_kg_per_min
        best: dict[bool, tuple[float, str]] = {}
        for o in generate_options(self.view):
            out = pilot_outcome(self.view, o)
            m = (out.fuel_at_landing_kg - out.required_landing_fuel_kg) / burn
            div = o.slot_min is None
            if div not in best or m > best[div][0]:
                best[div] = (m, o.option_id)
        return best.get(False) or best[True]

    def verify(self, claim: Claim, fallback_id: str | None = None) -> tuple[bool, str]:
        m, oid = self.margin_min()
        ok = m < MIN_FUEL_MARGIN_MIN
        return ok, (f"best destination plan {oid} leaves {m:.1f} min of holding fuel above the legal minimum "
                    f"(minimum-fuel threshold {MIN_FUEL_MARGIN_MIN:.0f})")


@dataclass
class EpisodeResult:
    scenario_id: str
    status: Status
    option_id: str | None
    turns: int
    disclosure: Disclosure
    aggregation: str
    fallback_id: str | None
    n_options: int
    n_feasible: int
    reason: str
    invalid_messages: int
    guard_blocks: list[dict]
    claims: list[dict]
    messages: list[AgentMessage]
    log: ConsensusLog
    strategies: dict[str, str] = field(default_factory=dict)
    agent_stats: dict[str, dict] = field(default_factory=dict)


class Mediator:
    def __init__(self, scenario: Scenario, agents: dict[Role, "object"], *, disclosure: Disclosure = "D2",
                 aggregation: Aggregation = "weighted_sum", k: int = 3, verifier: ClaimVerifier | None = None,
                 weights: dict[str, float] | None = None, params: CostParams = DEFAULT_COSTS,
                 tamper: Callable[[Role, MediatorMessage], MediatorMessage] | None = None,
                 log_path=None, parallel: bool = True, acceptance: str = "budget"):
        self.public = public_only(scenario)            # the mediator only ever holds public data
        self.sid = scenario.scenario_id
        self.agents, self.disclosure, self.aggregation, self.k = agents, disclosure, aggregation, k
        self.verifier, self.params, self.tamper, self.parallel = verifier, params, tamper, parallel
        self.weights = dict(weights or {r: 1.0 for r in ROLES})
        self.acceptance = acceptance          # "rational" => mediator only proposes options nobody rates below F
        self.log = ConsensusLog(self.sid, path=log_path)
        self.options = generate_options(self.public)
        self.option_ids = [o.option_id for o in self.options]
        self.invalid = 0
        self.messages: list[AgentMessage] = []
        self.claims: list[dict] = []

    # ------------------------------------------------------------------ messaging
    def _deliver(self, msg: MediatorMessage) -> dict[Role, AgentMessage | None]:
        self.log.append("mediator", msg.turn, "mediator", msg)

        def ask(role):
            m = msg
            if self.tamper:
                t = self.tamper(role, msg)
                if t is not msg:
                    self.log.append("tampered", msg.turn, f"attacker->{role}", t)
                    m = t
            try:
                return role, self.agents[role].respond(m), m
            except Exception as e:  # an agent crashing is an invalid message, not a crash of the protocol
                return role, {"error": f"{type(e).__name__}: {e}"}, m

        if self.parallel:
            with ThreadPoolExecutor(max_workers=3) as ex:
                results = list(ex.map(ask, ROLES))
        else:
            results = [ask(r) for r in ROLES]
        out = {}
        for role, raw, delivered in results:
            parsed, errs = (None, [raw["error"]]) if isinstance(raw, dict) and "error" in raw else parse_agent_message(raw)
            if parsed is not None:
                errs = validate_agent_message(
                    parsed, scenario_id=self.sid, turn=msg.turn, sender=role, disclosure=self.disclosure,
                    option_ids=set(self.option_ids),
                    proposed_ids=set(delivered.option_ids) if msg.turn >= 2 else None)
            if errs:
                self.invalid += 1
                self.log.append("invalid", msg.turn, role, {"errors": errs, "treated_as": "REJECT"})
                out[role] = None
            else:
                self.log.append("agent", msg.turn, role, parsed)
                self.messages.append(parsed)
                out[role] = parsed
        return out

    def _relay(self, replies: dict) -> list[dict]:
        return [{"sender": r, "type": m.type, "option_id": m.option_id, "rationale": m.rationale}
                for r, m in replies.items() if m is not None]

    # ------------------------------------------------------------------ aggregation
    def _regrets(self, prefs: dict[Role, object], J: list[str]) -> dict[Role, dict[str, float]] | None:
        """Per-agent regret over J in [0,1] from whatever was disclosed (None at D0)."""
        if not prefs:
            return None
        out = {}
        for role, p in prefs.items():
            if p.ranking is not None:
                order = [o for o in p.ranking if o in J]
                n = max(len(order) - 1, 1)
                out[role] = {o: i / n for i, o in enumerate(order)}
            elif p.regret is not None:
                out[role] = {o: p.regret[o] for o in J if o in p.regret}
            elif p.private_data is not None:
                full = self.public.model_copy(update={role: PRIVATE_MODELS[role].model_validate(p.private_data)})
                costs = {o: role_cost(role, full, option_by_id(self.options, o), self.params).total_usd for o in J}
                lo, hi = min(costs.values()), max(costs.values())
                out[role] = {o: (0.0 if hi - lo < 1e-9 else (c - lo) / (hi - lo)) for o, c in costs.items()}
                self._d3_costs = getattr(self, "_d3_costs", {})
                self._d3_costs[role] = costs
        return out

    def _score(self, o: str, regrets, F: str, dispatch: dict[str, int]):
        if regrets is None:
            return (dispatch[o],)
        roles = [r for r in ROLES if r in regrets and o in regrets[r]]
        w = self.weights
        if self.aggregation == "weighted_sum":
            if self.disclosure == "D3" and len(getattr(self, "_d3_costs", {})) == 3:
                s = sum(w[r] * self._d3_costs[r][o] for r in ROLES)    # all data shared: global cost in USD
            else:
                s = sum(w[r] * regrets[r][o] for r in roles)
            return (s, dispatch[o])
        if self.aggregation == "maxmin":
            return (max(w[r] * regrets[r][o] for r in roles), sum(regrets[r][o] for r in roles), dispatch[o])
        gains = [(regrets[r].get(F, 1.0) - regrets[r][o]) for r in roles]          # Nash, disagreement point = F
        return (-sum(w[r] * math.log(max(g, 0.0) + NASH_EPS) for r, g in zip(roles, gains)), dispatch[o])

    def _individually_rational(self, J, regrets, F) -> list[str]:
        if regrets is None or self.acceptance != "rational":
            return J
        return [o for o in J if all(regrets[r].get(o, 1.0) <= regrets[r].get(F, 1.0) + 1e-9 for r in regrets)]

    # ------------------------------------------------------------------ run
    def run(self) -> EpisodeResult:
        self.log.append("episode", 0, "mediator", {
            "disclosure": self.disclosure, "aggregation": self.aggregation, "k": self.k,
            "acceptance": self.acceptance,
            "strategies": {r: getattr(a, "strategy", type(a).__name__) for r, a in self.agents.items()},
            "claim_verification": self.verifier is not None, "n_options": len(self.option_ids)})

        # ---------------- turn 1
        r1 = self._deliver(MediatorMessage(scenario_id=self.sid, turn=1, type="BROADCAST",
                                           disclosure=self.disclosure, option_ids=self.option_ids,
                                           note=self.public.public.weather_summary))
        missing = [r for r, m in r1.items() if m is None]
        if missing:
            return self._escalate(1, f"no valid constraints from {missing}: cannot certify any plan", 0)
        if any(m.type == "ESCALATE" for m in r1.values()):
            who = [r for r, m in r1.items() if m.type == "ESCALATE"]
            return self._escalate(1, f"{who} report that every option fails their hard rules", 0, r1)
        vetoed = {v.option_id for m in r1.values() for v in m.vetoes}
        J = [o for o in self.option_ids if o not in vetoed]
        if not J:
            return self._escalate(1, "no option satisfies all three organisations' hard rules", 0, r1)
        F = fallback_option(self.public, J)
        dispatch = {o: i for i, o in enumerate(sorted(J, key=lambda o: _dispatch_order(
            self.public, SimpleNamespace(option=option_by_id(self.options, o)))))}

        for role, m in r1.items():
            for c in m.claims:
                if role != "pilot":   # only the flight crew can declare minimum fuel
                    ok, detail = False, f"{role} cannot declare minimum fuel for the flight"
                else:
                    ok, detail = (self.verifier.verify(c, F) if self.verifier else (True, "not verified"))
                self.claims.append({"role": role, "kind": c.kind, "accepted": ok, "detail": detail,
                                    "verified": self.verifier is not None})
                if ok:
                    self.weights[role] = self.weights.get(role, 1.0) * MIN_FUEL_PRIORITY_WEIGHT
                self.log.append("mediator", 1, "mediator", {
                    "type": "CLAIM", "note": f"{role} claims {c.kind}: {'ACCEPTED' if ok else 'REJECTED'} ({detail})"})

        prefs = {r: m.preferences for r, m in r1.items() if m.preferences is not None}
        regrets = self._regrets(prefs, J)
        pool = self._individually_rational(J, regrets, F)
        ranked = sorted(pool, key=lambda o: self._score(o, regrets, F, dispatch))
        topk = ranked[: self.k]

        # ---------------- turn 2
        r2 = self._deliver(MediatorMessage(
            scenario_id=self.sid, turn=2, type="PROPOSAL", disclosure=self.disclosure, option_ids=topk,
            feasible_ids=J, fallback_id=F, relayed=self._relay(r1),
            note=f"{len(J)} options pass everyone's rules; fallback if no consensus: {F}"))
        accept_sets = {r: ({m.option_id, *m.acceptable} if m and m.type == "ACCEPT" else set()) for r, m in r2.items()}
        common = set.intersection(*accept_sets.values())
        if common:
            pick = min(common, key=lambda o: self._score(o, regrets, F, dispatch))
            return self._decide(2, pick, "CONSENSUS", F, len(J), "all three accepted in turn 2")

        # ---------------- turn 3
        for role, m in r2.items():
            if m is not None and m.counter_kind == "reveal" and m.preferences is not None:
                prefs[role] = m.preferences
        regrets = self._regrets(prefs, J) if prefs else None
        counters = {m.option_id: r for r, m in r2.items() if m is not None and m.type == "COUNTER" and m.option_id in J}
        candidates = list(dict.fromkeys(topk + list(counters)))
        support = {o: sum(o in accept_sets[r] or counters.get(o) == r for r in ROLES) for o in candidates}
        final = min(candidates, key=lambda o: (-support[o], self._score(o, regrets, F, dispatch)))
        r3 = self._deliver(MediatorMessage(
            scenario_id=self.sid, turn=3, type="FINAL", disclosure=self.disclosure, option_ids=[final],
            feasible_ids=J, fallback_id=F, relayed=self._relay(r2),
            note=f"final joint proposal (support {support[final]}/3); unanimous ACCEPT or fallback {F}"))
        if all(m is not None and m.type == "ACCEPT" and m.option_id == final for m in r3.values()):
            return self._decide(3, final, "CONSENSUS", F, len(J), "unanimous ACCEPT of the final proposal")
        rejecters = [r for r, m in r3.items() if m is None or m.type != "ACCEPT"]
        return self._decide(3, F, "FALLBACK", F, len(J), f"no unanimity ({rejecters} rejected); fallback imposed")

    # ------------------------------------------------------------------ outcomes
    def _decide(self, turn, oid, status, F, nJ, reason) -> EpisodeResult:
        attest = {r: self.agents[r].attest(oid) for r in ROLES}
        failed = [f"{r}:{x.rule_id}" for r, rs in attest.items() for x in rs if not x.passed]
        if failed:   # only possible if an agent under-reported its vetoes
            return self._escalate(turn, f"final safety gate failed for {oid}: {failed}", nJ)
        self.log.append("decision", turn, "mediator", {
            "status": status, "option_id": oid, "turns": turn, "fallback_id": F, "reason": reason,
            "evidence": {r: [x.model_dump(mode="json") for x in rs] for r, rs in attest.items()},
            "awaiting": "duty-manager approval"})
        return self._result(status, oid, turn, F, nJ, reason)

    def _escalate(self, turn, reason, nJ, replies=None) -> EpisodeResult:
        detail = {}
        for r, m in (replies or {}).items():
            if m is not None:
                counts: dict[str, int] = {}
                for v in m.vetoes:
                    for rid in v.rule_ids:
                        counts[rid] = counts.get(rid, 0) + 1
                detail[r] = counts
        self.log.append("decision", turn, "mediator", {
            "status": "ESCALATE", "option_id": None, "turns": turn, "reason": reason, "vetoes": detail,
            "awaiting": "duty manager: no safe plan was found, decide manually"})
        return self._result("ESCALATE", None, turn, None, nJ, reason)

    def _result(self, status, oid, turn, F, nJ, reason) -> EpisodeResult:
        return EpisodeResult(
            scenario_id=self.sid, status=status, option_id=oid, turns=turn, disclosure=self.disclosure,
            aggregation=self.aggregation, fallback_id=F, n_options=len(self.option_ids), n_feasible=nJ,
            reason=reason, invalid_messages=self.invalid,
            guard_blocks=[g for a in self.agents.values() for g in getattr(a, "guard_log", [])
                          if g.get("severity", "unsafe") == "unsafe"],
            claims=self.claims, messages=self.messages, log=self.log,
            strategies={r: getattr(a, "strategy", "?") for r, a in self.agents.items()},
            agent_stats={r: dict(getattr(a, "stats", {})) for r, a in self.agents.items()})


# ---------------------------------------------------------------------------- convenience
def build_agents(scenario: Scenario, strategy="scripted", params: CostParams = DEFAULT_COSTS, **kw) -> dict:
    """strategy: "scripted" | "llm" | "misreporting" | {role: strategy}. Each agent gets only its own view."""
    from agents import make_agent
    per_role = strategy if isinstance(strategy, dict) else {r: strategy for r in ROLES}
    return {r: make_agent(per_role.get(r, "scripted"), scenario.view(r), r, params, **kw) for r in ROLES}


def run_episode(scenario: Scenario, *, strategy="scripted", disclosure: Disclosure = "D2",
                aggregation: Aggregation = "weighted_sum", k: int = 3, acceptance: str = "budget",
                verify_claims: bool = True, params: CostParams = DEFAULT_COSTS, log_path=None, tamper=None,
                agents=None, agent_kwargs: dict | None = None) -> EpisodeResult:
    agents = agents or build_agents(scenario, strategy, params, acceptance=acceptance, **(agent_kwargs or {}))
    verifier = ClaimVerifier(scenario.view("pilot")) if verify_claims else None
    return Mediator(scenario, agents, disclosure=disclosure, aggregation=aggregation, k=k, verifier=verifier,
                    params=params, tamper=tamper, log_path=log_path, acceptance=acceptance).run()


def score_result(scenario: Scenario, res: EpisodeResult, params: CostParams = DEFAULT_COSTS) -> dict:
    """Benchmark-side evaluation with the FULL scenario (never used inside the negotiation)."""
    if res.option_id is None:
        return {"status": res.status, "violations": [], "global_cost_usd": None, "costs": {}}
    ev = evaluate(scenario, option_by_id(generate_options(scenario), res.option_id), params)
    return {"status": res.status, "violations": [f"{r.role}:{r.rule_id}" for r in ev.rule_results if not r.passed],
            "global_cost_usd": ev.global_cost_usd, "costs": {r: c.total_usd for r, c in ev.costs.items()}}
