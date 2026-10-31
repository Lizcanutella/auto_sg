"""Offline stand-ins for the Anthropic client (tests, adversarial track, CI without an API key).

FakeClient mimics `client.messages.create(...)` and delegates each turn to a policy:
    policy(payload: dict, tool_results: list[str]) -> dict reply | ("tool", name, input) | Exception
Ready-made policies:
    sensible      picks the deterministic recommendation from the candidate table
    compliant     obeys any instruction like "ACCEPT <option>" found in UNTRUSTED text (worst case)
    garbage       returns invalid JSON
    broken        raises an API-style error
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

_ORDER = re.compile(r"\b(?:ACCEPT|PROPOSE|accept|propose)\s+(?:option\s+)?([A-Za-z_]+@\d{2}:\d{2}/\w+/\w+|\w+/divert)")


def _resp(content, stop_reason, usage=(1000, 100)):
    return SimpleNamespace(content=content, stop_reason=stop_reason,
                           usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]))


def _text(obj) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=obj if isinstance(obj, str) else json.dumps(obj))


class FakeClient:
    def __init__(self, policy):
        self.policy = policy
        self.messages = self
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        msgs = kw["messages"]
        payload = json.loads(msgs[0]["content"])
        tool_results = [b["content"] for m in msgs[1:] if m["role"] == "user" for b in m["content"]]
        out = self.policy(payload, tool_results)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, tuple) and out[0] == "tool":
            return _resp([SimpleNamespace(type="tool_use", id=f"tu_{self.calls}", name=out[1], input=out[2])], "tool_use")
        return _resp([_text(out)], "end_turn")


def _reply(action, option_id="", acceptable=(), counter_kind="none", claims=(), rationale=""):
    return {"action": action, "option_id": option_id or "", "acceptable": list(acceptable),
            "counter_kind": counter_kind, "claims": list(claims), "rationale": rationale}


def sensible(payload, tool_results):
    """Behaves like the scripted agent, using only what is in the payload; inspects one option first."""
    cands = payload["candidates"]
    legal = payload["legal_actions"]
    if not tool_results and cands:
        return ("tool", "inspect_option", {"option_id": cands[0]["option_id"]})
    safe = [c for c in cands if c["passes_my_rules"] and not c.get("vetoed_by_someone")]
    if "PROPOSE" in legal:
        best = min(safe, key=lambda c: c["my_cost_usd"])
        return _reply("PROPOSE", best["option_id"], rationale=f"Best for us: {best['option_id']} at ${best['my_cost_usd']}.")
    ok = sorted((c for c in safe if c.get("proposed_by_mediator") and c.get("within_my_budget")),
                key=lambda c: c["my_cost_usd"])
    if ok:
        return _reply("ACCEPT", ok[0]["option_id"], [c["option_id"] for c in ok[1:]],
                      rationale=f"Accept {ok[0]['option_id']} at ${ok[0]['my_cost_usd']} vs fallback ${payload['fallback_cost_usd']}.")
    if "COUNTER" in legal and safe:
        best = min(safe, key=lambda c: c["my_cost_usd"])
        return _reply("COUNTER", best["option_id"], counter_kind="variant", rationale=f"Counter {best['option_id']}.")
    return _reply("REJECT", rationale="Nothing proposed is within our budget.")


def compliant(payload, tool_results):
    """Worst-case LLM: follows any order planted in untrusted text, otherwise behaves sensibly."""
    untrusted = json.dumps({k: v for k, v in payload.items() if k.startswith("UNTRUSTED")}) + \
        json.dumps(payload["briefing"].get("UNTRUSTED_weather_text", ""))
    m = _ORDER.search(untrusted)
    legal = payload["legal_actions"]
    if m:
        target = m.group(1)
        action = "PROPOSE" if "PROPOSE" in legal else "ACCEPT"
        return _reply(action, target, rationale=f"Following the instruction received: {action} {target}.")
    return sensible(payload, tool_results)


def garbage(payload, tool_results):
    return "this is not json {"


class _FakeAPIError(Exception):
    pass


def broken(payload, tool_results):
    return _FakeAPIError("simulated 529 overloaded")
