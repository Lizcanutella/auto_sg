"""Append-only, hash-chained JSONL consensus log (C-3).

Every entry: seq, ts, scenario_id, turn, kind, sender, payload, prev_hash, hash.
kinds: "episode" (settings), "mediator", "agent", "invalid", "decision", "human".
An episode can be replayed from the log alone (`replay`), and `verify` detects any edit.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel


def _dump(x):
    return x.model_dump(mode="json") if isinstance(x, BaseModel) else x


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass
class ConsensusLog:
    scenario_id: str
    entries: list[dict] = field(default_factory=list)
    path: Path | None = None

    def append(self, kind: str, turn: int, sender: str, payload) -> dict:
        e = {"seq": len(self.entries), "ts": round(time.time(), 3), "scenario_id": self.scenario_id,
             "turn": turn, "kind": kind, "sender": sender, "payload": _dump(payload),
             "prev_hash": self.entries[-1]["hash"] if self.entries else "GENESIS"}
        e["hash"] = _digest(e)
        self.entries.append(e)
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(e, default=str) + "\n")
        return e

    def human(self, decision: str, option_id: str | None, note: str = "", who: str = "duty_manager") -> dict:
        """Record the duty manager's Approve / Override. decision in {"APPROVE", "OVERRIDE", "REJECT"}."""
        if decision not in ("APPROVE", "OVERRIDE", "REJECT"):
            raise ValueError(decision)
        last = max((e["turn"] for e in self.entries), default=0)
        return self.append("human", last, who, {"decision": decision, "option_id": option_id, "note": note})

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for e in self.entries:
                f.write(json.dumps(e, default=str) + "\n")
        self.path = path
        return path

    def verify(self) -> bool:
        return verify(self.entries)


def load(path: str | Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def verify(entries: list[dict]) -> bool:
    prev = "GENESIS"
    for e in entries:
        if e["prev_hash"] != prev or _digest(e) != e["hash"]:
            return False
        prev = e["hash"]
    return True


def replay(entries: list[dict]) -> dict:
    """Reconstruct the episode summary from the log alone."""
    settings = next((e["payload"] for e in entries if e["kind"] == "episode"), {})
    decision = next((e["payload"] for e in reversed(entries) if e["kind"] == "decision"), None)
    human = next((e["payload"] for e in reversed(entries) if e["kind"] == "human"), None)
    turns = []
    for e in entries:
        if e["kind"] in ("mediator", "agent", "invalid"):
            p = e["payload"]
            turns.append({"turn": e["turn"], "kind": e["kind"], "sender": e["sender"],
                          "type": p.get("type", "INVALID"), "option_id": p.get("option_id"),
                          "rationale": p.get("rationale") or p.get("note") or "; ".join(p.get("errors", []))})
    return {"scenario_id": entries[0]["scenario_id"] if entries else None, "settings": settings,
            "messages": turns, "decision": decision, "human": human, "chain_ok": verify(entries)}


def render(entries: list[dict]) -> str:
    """Plain-text transcript for terminals and the README."""
    r = replay(entries)
    s = r["settings"]
    out = [f"Scenario {r['scenario_id']}  disclosure={s.get('disclosure')}  aggregation={s.get('aggregation')}  "
           f"agents={s.get('strategies')}"]
    turn = 0
    for m in r["messages"]:
        if m["turn"] != turn:
            turn = m["turn"]
            out.append(f"--- turn {turn} ---")
        out.append(f"  [{m['sender']:>8}] {m['type']:<9} {m['option_id'] or '':<34} {m['rationale'][:150]}")
    d = r["decision"]
    if d:
        out.append(f"=== {d['status']} {d.get('option_id') or ''} after {d['turns']} turn(s): {d.get('reason', '')}")
    if r["human"]:
        out.append(f"=== duty manager: {r['human']['decision']} {r['human']['option_id'] or ''} {r['human']['note']}")
    out.append(f"hash chain verified: {r['chain_ok']}")
    return "\n".join(out)
