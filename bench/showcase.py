"""Regenerate the showcase consensus logs used by docs/RESULTS.md and the demo page.

  python -m bench.showcase            # needs results/logs from bench.run; the live run needs an API key

Writes results/demo_real_A0266.jsonl (attack on ATC, worst-case mock LLM), results/demo_real_A0266_live_llm.jsonl
(live Claude, no attack), results/failure_real_A0325_d0.jsonl and results/escalation_ep3.jsonl.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from agents.mock_llm import FakeClient, compliant
from protocol import run_episode, score_result
from tracks import adversarial
from tracks.common import load_scenarios

RES = Path("results")


def main():
    sc = {s.scenario_id: s for s in load_scenarios("data/scenarios.jsonl")}
    s = sc["A0266"]
    s2, tamper, unsafe = adversarial.build_case(s, "pressure", "atc")
    r = run_episode(s2, strategy={"atc": "llm"}, tamper=tamper, disclosure="D2", aggregation="nash",
                    agent_kwargs={"client": FakeClient(compliant)})
    r.log.write(RES / "demo_real_A0266.jsonl")
    print("attack demo:", r.status, r.option_id, score_result(s2, r)["global_cost_usd"], "unsafe blocked:", unsafe)
    r = run_episode(s, strategy="llm", disclosure="D2", aggregation="nash")
    r.log.write(RES / "demo_real_A0266_live_llm.jsonl")
    print("live demo:", r.status, r.option_id, score_result(s, r)["global_cost_usd"], r.claims)
    shutil.copy(RES / "logs/A0325__scripted__D0__nash__budget.jsonl", RES / "failure_real_A0325_d0.jsonl")
    ep3 = load_scenarios()[2]
    run_episode(ep3).log.write(RES / "escalation_ep3.jsonl")
    print("wrote showcase logs")


if __name__ == "__main__":
    main()
