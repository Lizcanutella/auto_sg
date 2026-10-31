"""Run one negotiation and print the consensus log.

  python -m protocol.run fixtures/episode_001.json --level D2 --agg nash
  python -m protocol.run scenarios.jsonl --index 7 --agents llm --log runs/ep7.jsonl --decision APPROVE
  python -m protocol.run --replay runs/ep7.jsonl
"""
from __future__ import annotations

import argparse
import json

from baselines import best_possible, fcfs_rbs
from contracts import Scenario
from protocol import log as clog
from protocol import run_episode, score_result


def load(path: str, index: int) -> Scenario:
    if path.endswith(".jsonl"):
        with open(path) as f:
            return Scenario.model_validate(json.loads([line for line in f if line.strip()][index]))
    return Scenario.model_validate_json(open(path).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--level", default="D2", choices=["D0", "D1", "D2", "D3"])
    ap.add_argument("--agg", default="weighted_sum", choices=["weighted_sum", "maxmin", "nash"])
    ap.add_argument("--acceptance", default="budget", choices=["rational", "budget", "cooperative"])
    ap.add_argument("--agents", default="scripted", help="scripted | llm | misreporting | role=strategy,...")
    ap.add_argument("--no-verify", action="store_true", help="do not verify min-fuel claims")
    ap.add_argument("--log")
    ap.add_argument("--decision", choices=["APPROVE", "OVERRIDE", "REJECT"], help="duty manager decision to record")
    ap.add_argument("--replay")
    a = ap.parse_args()

    if a.replay:
        entries = clog.load(a.replay)
        print(clog.render(entries))
        return
    s = load(a.scenario, a.index)
    strategy = dict(kv.split("=") for kv in a.agents.split(",")) if "=" in a.agents else a.agents
    res = run_episode(s, strategy=strategy, disclosure=a.level, aggregation=a.agg, acceptance=a.acceptance,
                      verify_claims=not a.no_verify)
    if a.decision:
        res.log.human(a.decision, res.option_id)
    if a.log:
        res.log.write(a.log)
    print(clog.render(res.log.entries))
    sc = score_result(s, res)
    f, b = fcfs_rbs.plan(s), best_possible.plan(s)
    if res.option_id and f.chosen and b.chosen:
        cf, cb, cs = f.chosen.global_cost_usd, b.chosen.global_cost_usd, sc["global_cost_usd"]
        gap = "n/a" if cf - cb < 1e-6 else f"{(cf - cs) / (cf - cb):.0%}"
        print(f"global cost: negotiated ${cs:,.0f} | FCFS ${cf:,.0f} | best possible ${cb:,.0f} | gap closed {gap}")
    print(f"violations in final plan: {sc['violations'] or 'none'} | invalid messages: {res.invalid_messages} | "
          f"guard blocks: {len(res.guard_blocks)} | claims: {res.claims or 'none'}")
    for role, st in res.agent_stats.items():
        if st:
            print(f"  {role} LLM: {st['calls']} calls, {st['tool_calls']} tool calls, "
                  f"{st['input_tokens']}+{st['output_tokens']} tokens, {st['latency_s']:.1f}s, "
                  f"fallbacks {len(st['fallbacks'])}, unsupported numbers {len(st['unsupported_numbers'])}")


if __name__ == "__main__":
    main()
