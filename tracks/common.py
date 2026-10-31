"""Scenario loading shared by the tracks: fixtures by default, or a scenarios.jsonl from workstream A."""
from __future__ import annotations

import json
from pathlib import Path

from contracts import Scenario

ROOT = Path(__file__).resolve().parent.parent


def load_scenarios(path: str | None = None, limit: int | None = None) -> list[Scenario]:
    if path is None:
        files = sorted((ROOT / "fixtures").glob("episode_*.json"))
        out = [Scenario.model_validate_json(f.read_text()) for f in files]
    else:
        with open(path) as f:
            out = [Scenario.model_validate(json.loads(line)) for line in f if line.strip()]
    return out[:limit] if limit else out
