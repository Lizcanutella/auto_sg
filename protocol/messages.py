"""Message schemas and validation (C-1).

Two message families:
- AgentMessage: sent by an organisation's agent to the mediator.
- MediatorMessage: sent by the mediator to all agents.

`validate_agent_message` is run by the mediator on every message it receives. A message
that fails is logged as invalid and treated as REJECT (see mediator), so a broken or
manipulated agent can stall agreement but can never push a plan through.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts import Role, RuleResult

Disclosure = Literal["D0", "D1", "D2", "D3"]
DISCLOSURE_ORDER = {"D0": 0, "D1": 1, "D2": 2, "D3": 3}
AgentMsgType = Literal["PROPOSE", "COUNTER", "ACCEPT", "REJECT", "ESCALATE"]
CounterKind = Literal["concede", "reveal", "variant"]

# message types an agent may send in each turn
ALLOWED_TYPES: dict[int, tuple[str, ...]] = {
    1: ("PROPOSE", "ESCALATE"),
    2: ("ACCEPT", "COUNTER", "REJECT"),
    3: ("ACCEPT", "REJECT"),
}
MAX_RATIONALE_CHARS = 600


class _Msg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Veto(_Msg):
    option_id: str
    rule_ids: list[str]


class Preferences(_Msg):
    """What an agent discloses about its private preferences, by disclosure level.

    D0: nothing (vetoes only).  D1: ranking of its non-vetoed options, best first.
    D2: normalised regret per non-vetoed option, 0 = its best, 1 = its worst (unit-free).
    D3: its raw private data block, so the mediator can compute everything itself.
    """
    level: Disclosure
    ranking: list[str] | None = None
    regret: dict[str, float] | None = None
    private_data: dict | None = None


class Claim(_Msg):
    kind: Literal["min_fuel"]          # pilot: "I am at minimum fuel, give me priority"
    detail: str = ""


class AgentMessage(_Msg):
    scenario_id: str
    turn: int = Field(ge=1, le=3)
    sender: Role
    type: AgentMsgType
    option_id: str | None = None       # PROPOSE: own first choice; ACCEPT: accepted option; COUNTER: counter-option
    acceptable: list[str] = Field(default_factory=list)   # ACCEPT (turn 2): other proposed options also acceptable
    vetoes: list[Veto] = Field(default_factory=list)      # turn 1: options failing the sender's own hard rules
    preferences: Preferences | None = None                # turn 1, or a COUNTER of kind "reveal"
    counter_kind: CounterKind | None = None
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[RuleResult] = Field(default_factory=list)  # sender's own rule results for option_id
    rationale: str = Field(default="", max_length=MAX_RATIONALE_CHARS)
    author: str = "scripted"           # "scripted" | "llm:<model>" | "llm-fallback:<reason>"
    guard_notes: list[str] = Field(default_factory=list)  # what the sender's hard guard changed or blocked


class MediatorMessage(_Msg):
    scenario_id: str
    turn: int = Field(ge=1, le=3)
    type: Literal["BROADCAST", "PROPOSAL", "FINAL", "DECISION", "ESCALATE"]
    disclosure: Disclosure
    option_ids: list[str] = Field(default_factory=list)   # BROADCAST: all; PROPOSAL: top-k; FINAL/DECISION: one
    feasible_ids: list[str] | None = None                  # options nobody vetoed (after turn 1)
    fallback_id: str | None = None                         # what is imposed if there is no consensus
    relayed: list[dict] = Field(default_factory=list)      # peers' (sender, type, option_id, rationale), untrusted text
    note: str = ""


def parse_agent_message(raw: dict | AgentMessage) -> tuple[AgentMessage | None, list[str]]:
    if isinstance(raw, AgentMessage):
        return raw, []
    try:
        return AgentMessage.model_validate(raw), []
    except ValidationError as e:
        return None, [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]


def validate_agent_message(msg: AgentMessage, *, scenario_id: str, turn: int, sender: Role,
                           disclosure: Disclosure, option_ids: set[str], proposed_ids: set[str] | None) -> list[str]:
    """Protocol-level checks the mediator can do without anyone's private data. Returns errors."""
    errs = []
    if msg.scenario_id != scenario_id:
        errs.append(f"scenario_id {msg.scenario_id!r} != {scenario_id!r}")
    if msg.sender != sender:
        errs.append(f"sender {msg.sender!r} does not match channel {sender!r}")
    if msg.turn != turn:
        errs.append(f"turn {msg.turn} sent in turn {turn}")
    if msg.type not in ALLOWED_TYPES[turn]:
        errs.append(f"{msg.type} not allowed in turn {turn} (allowed: {ALLOWED_TYPES[turn]})")
    referenced = [msg.option_id] if msg.option_id else []
    referenced += msg.acceptable + [v.option_id for v in msg.vetoes]
    unknown = [o for o in referenced if o not in option_ids]
    if unknown:
        errs.append(f"unknown option ids: {unknown[:3]}")
    if msg.type in ("PROPOSE", "ACCEPT", "COUNTER") and not msg.option_id:
        errs.append(f"{msg.type} needs an option_id")
    if msg.type == "ACCEPT" and proposed_ids is not None:
        outside = [o for o in [msg.option_id, *msg.acceptable] if o and o not in proposed_ids]
        if outside:
            errs.append(f"ACCEPT references options that were not proposed: {outside[:3]}")
    if msg.type == "COUNTER" and msg.counter_kind is None:
        errs.append("COUNTER needs a counter_kind")
    vetoed = {v.option_id for v in msg.vetoes}
    if msg.type in ("PROPOSE", "ACCEPT", "COUNTER") and msg.option_id in vetoed:
        errs.append(f"{msg.type} of an option the sender itself vetoed")
    p = msg.preferences
    if p is not None:
        allowed = DISCLOSURE_ORDER[disclosure] + (3 if msg.counter_kind == "reveal" else 0)
        if DISCLOSURE_ORDER[p.level] > allowed:
            errs.append(f"preferences at {p.level} exceed the episode's disclosure level {disclosure}")
        if p.regret is not None:
            bad = [o for o, r in p.regret.items() if not (0.0 <= r <= 1.0) or o not in option_ids]
            if bad:
                errs.append(f"regret must be in [0,1] for known options: {bad[:3]}")
        if p.ranking is not None and any(o not in option_ids for o in p.ranking):
            errs.append("ranking contains unknown option ids")
    return errs
