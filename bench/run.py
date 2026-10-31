"""Benchmark runner (D-1): systems x disclosure levels x aggregation rules -> results/results.parquet.

  python -m bench.run                                     # fixtures, scripted, all levels/rules
  python -m bench.run --scenarios data/scenarios.jsonl    # workstream A's scenarios
  python -m bench.run --llm-subset 30 --llm-levels D0,D2  # + LLM agents on a fixed subset
  python -m bench.run --tracks                             # + adversarial (C) and misreporting (D) tracks

Every episode's consensus log is written to results/logs/ (the UI plays them back). Rows are cached
in results/cache/ keyed by scenario content + settings, so re-running is cheap and LLM episodes are
never paid for twice (--no-cache to force).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from baselines import best_possible, fcfs_rbs, siloed
from contracts import ROLES, Scenario
from protocol import run_episode, score_result
from sim import evaluate, evaluate_all, generate_options, option_by_id
from sim.params import DEFAULT_COSTS, CostParams
from tracks.common import load_scenarios

OUT = Path("results")
GAP_REFERENCE = "siloed-v1"   # in the cache key: rows cached under the old FCFS reference are not reused
LEVELS = ("D0", "D1", "D2", "D3")
AGGS = ("weighted_sum", "maxmin", "nash")


def _key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:20]


def _scenario_hash(s: Scenario) -> str:
    return hashlib.sha256(s.model_dump_json().encode()).hexdigest()[:12]


def baseline_rows(s: Scenario, p: CostParams) -> tuple[list[dict], dict]:
    """Siloed, FCFS and best-possible rows + the reference numbers every negotiated row is compared with."""
    ev = evaluate_all(s, p)
    feas = [e for e in ev if e.feasible]
    ref = {"siloed": None, "fcfs": None, "best": None, "role_min": {}}
    rows = []
    for name, mod in (("siloed", siloed), ("fcfs", fcfs_rbs), ("best_possible", best_possible)):
        t0 = time.time()
        r = mod.plan(s, p)
        row = _base_row(s, name, "-", "-", "-")
        row.update(status="CONSENSUS" if r.status == "plan" else "ESCALATE",
                   option_id=r.chosen.option.option_id if r.chosen else None, turns=0,
                   n_options=r.n_options, n_feasible=r.n_feasible, wall_s=time.time() - t0)
        if r.chosen:
            row["global_cost_usd"] = r.chosen.global_cost_usd
            for role, c in r.chosen.costs.items():
                row[f"cost_{role}"] = c.total_usd
        rows.append(row)
        ref["best" if name == "best_possible" else name] = row
    for role in ROLES:
        ref["role_min"][role] = min((e.costs[role].total_usd for e in feas), default=None)
    return rows, ref


def _base_row(s: Scenario, system: str, level: str, agg: str, acceptance: str) -> dict:
    f = s.public.focal
    return {"scenario_id": s.scenario_id, "track": s.track, "airport": f.destination, "airline": f.airline,
            "decision_point": s.public.decision_point, "system": system, "disclosure": level,
            "aggregation": agg, "acceptance": acceptance, "status": None, "option_id": None, "turns": None,
            "global_cost_usd": math.nan, "cost_atc": math.nan, "cost_pilot": math.nan, "cost_ground": math.nan,
            "violations": 0, "violation_ids": "", "n_options": None, "n_feasible": None}


def negotiated_row(s: Scenario, system: str, level: str, agg: str, acceptance: str, ref: dict,
                   p: CostParams, log_dir: Path, agent_kwargs: dict | None = None) -> dict:
    strategy = "llm" if system == "llm" else "scripted"
    t0 = time.time()
    res = run_episode(s, strategy=strategy, disclosure=level, aggregation=agg, acceptance=acceptance,
                      params=p, agent_kwargs=agent_kwargs)
    wall = time.time() - t0
    sc = score_result(s, res, p)
    log_path = log_dir / f"{s.scenario_id}__{system}__{level}__{agg}__{acceptance}.jsonl"
    res.log.write(log_path)
    row = _base_row(s, system, level, agg, acceptance)
    row.update(status=res.status, option_id=res.option_id, turns=res.turns, n_options=res.n_options,
               n_feasible=res.n_feasible, fallback_id=res.fallback_id, reason=res.reason,
               violations=len(sc["violations"]), violation_ids=",".join(sc["violations"]),
               invalid_messages=res.invalid_messages, guard_blocks=len(res.guard_blocks),
               claims_accepted=sum(c["accepted"] for c in res.claims), wall_s=wall, log_path=str(log_path))
    if sc["global_cost_usd"] is not None:
        row["global_cost_usd"] = sc["global_cost_usd"]
        for role, c in sc["costs"].items():
            row[f"cost_{role}"] = c
            if ref["role_min"].get(role) is not None:
                row[f"regret_{role}"] = c - ref["role_min"][role]       # vs own best jointly-feasible option
    fb = res.fallback_id
    if fb and res.option_id:
        fb_costs = {r: c.total_usd for r, c in evaluate(s, option_by_id(generate_options(s), fb), p).costs.items()}
        for role in ROLES:
            row[f"concession_{role}"] = row[f"cost_{role}"] - fb_costs[role]    # >0: worse than fallback
    st = res.agent_stats
    if any(st.values()):
        row.update(
            llm_calls=sum(v.get("calls", 0) for v in st.values()),
            llm_tool_calls=sum(v.get("tool_calls", 0) for v in st.values()),
            llm_input_tokens=sum(v.get("input_tokens", 0) for v in st.values()),
            llm_output_tokens=sum(v.get("output_tokens", 0) for v in st.values()),
            llm_latency_s=sum(v.get("latency_s", 0.0) for v in st.values()),
            llm_fallbacks=sum(len(v.get("fallbacks", [])) for v in st.values()),
            llm_unsupported_numbers=sum(len(v.get("unsupported_numbers", [])) for v in st.values()),
            llm_attempted_unsafe=sum(v.get("attempted_unsafe", 0) for v in st.values()),
            llm_moves=sum(1 for m in res.messages),
        )
    _add_gap(row, ref)
    return row


def _add_gap(row: dict, ref: dict):
    """gap_closed: share of the price of silos (siloed - best) the system recovers.
    gap_closed_vs_fcfs: the same against FCFS, i.e. beyond what sharing data with simple rules gets."""
    b = ref["best"]
    row["best_cost_usd"] = b["global_cost_usd"] if b else math.nan
    for name, col in (("siloed", "gap_closed"), ("fcfs", "gap_closed_vs_fcfs")):
        r = ref[name]
        row[f"{name}_cost_usd"] = r["global_cost_usd"] if r else math.nan
        denom = row[f"{name}_cost_usd"] - row["best_cost_usd"]
        if row["status"] == "ESCALATE" or not denom or math.isnan(denom) or denom < 1e-6 or math.isnan(row["global_cost_usd"]):
            row[col] = math.nan
        else:
            row[col] = (row[f"{name}_cost_usd"] - row["global_cost_usd"]) / denom
    row["correct_escalation"] = (row["status"] == "ESCALATE") == (b is not None and b["status"] == "ESCALATE")


def _job(args):
    """One unit of work (runs in a worker process for scripted agents)."""
    s_json, system, level, agg, acceptance, p_json, log_dir, agent_kwargs = args
    s = Scenario.model_validate_json(s_json)
    p = CostParams.model_validate_json(p_json)
    _, ref = baseline_rows(s, p)
    return negotiated_row(s, system, level, agg, acceptance, ref, p, Path(log_dir), agent_kwargs)


def run(scenarios: list[Scenario], *, levels=LEVELS, aggs=AGGS, acceptance=("budget",), llm_subset: int = 0,
        llm_levels=("D0", "D2"), llm_aggs=("nash",), params: CostParams = DEFAULT_COSTS, out: Path = OUT,
        use_cache: bool = True, workers: int | None = None, llm_workers: int = 4, label: str = "main") -> pd.DataFrame:
    log_dir, cache_dir = out / "logs", out / "cache"
    log_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    p_json = params.model_dump_json()
    rows, jobs, llm_jobs = [], [], []
    # fixed LLM subset: the first N scenarios by a stable hash of their id (independent of file order)
    llm_ids = set(sorted((s.scenario_id for s in scenarios), key=lambda i: hashlib.md5(i.encode()).hexdigest())[:llm_subset])
    for s in scenarios:
        base, _ = baseline_rows(s, params)
        rows += base
        sh = _scenario_hash(s)
        for acc in acceptance:
            for lvl in levels:
                for agg in aggs:
                    jobs.append((s, "scripted", lvl, agg, acc))
            if s.scenario_id in llm_ids:
                for lvl in llm_levels:
                    for agg in llm_aggs:
                        llm_jobs.append((s, "llm", lvl, agg, acc))
    todo, todo_llm = [], []
    for kind, lst, dest in (("s", jobs, todo), ("l", llm_jobs, todo_llm)):
        for s, system, lvl, agg, acc in lst:
            from agents.llm import MODEL
            k = _key(_scenario_hash(s), system, lvl, agg, acc, p_json, MODEL if system == "llm" else "", GAP_REFERENCE)
            f = cache_dir / f"{k}.json"
            if use_cache and f.exists():
                rows.append(json.loads(f.read_text()))
            else:
                dest.append((f, (s.model_dump_json(), system, lvl, agg, acc, p_json, str(log_dir), None)))

    def save(f, row):
        row = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}
        f.write_text(json.dumps(row, default=str))
        rows.append(row)

    t0 = time.time()
    if todo:
        with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1)) as ex:
            for (f, _), row in zip(todo, ex.map(_job, [a for _, a in todo], chunksize=8)):
                save(f, row)
    if todo_llm:
        with ThreadPoolExecutor(max_workers=llm_workers) as ex:
            for (f, _), row in zip(todo_llm, ex.map(_job, [a for _, a in todo_llm])):
                save(f, row)
    df = pd.DataFrame(rows)
    df["run_label"] = label
    print(f"{len(scenarios)} scenarios, {len(df)} rows ({len(todo)} scripted + {len(todo_llm)} LLM episodes run, "
          f"rest cached) in {time.time() - t0:.1f}s")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", help="scenarios.jsonl from workstream A (default: fixtures)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--levels", default=",".join(LEVELS))
    ap.add_argument("--aggs", default=",".join(AGGS))
    ap.add_argument("--acceptance", default="budget", help="comma list of rational,budget,cooperative")
    ap.add_argument("--llm-subset", type=int, default=0, help="run LLM agents on this many scenarios")
    ap.add_argument("--llm-levels", default="D0,D2")
    ap.add_argument("--llm-aggs", default="nash")
    ap.add_argument("--tracks", action="store_true", help="also run adversarial (C) and misreporting (D) tracks")
    ap.add_argument("--tracks-live", action="store_true", help="include the live LLM in the adversarial track")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--workers", type=int)
    a = ap.parse_args()
    out = Path(a.out)
    scenarios = load_scenarios(a.scenarios, a.limit)
    df = run(scenarios, levels=a.levels.split(","), aggs=a.aggs.split(","), acceptance=a.acceptance.split(","),
             llm_subset=a.llm_subset, llm_levels=a.llm_levels.split(","), llm_aggs=a.llm_aggs.split(","),
             out=out, use_cache=not a.no_cache, workers=a.workers)
    df.to_parquet(out / "results.parquet")
    print(f"wrote {out / 'results.parquet'}")
    if a.tracks:
        from agents.mock_llm import FakeClient, compliant
        from tracks import adversarial, misreport
        strategies = {"scripted": lambda: ("scripted", {}),
                      "mock-compliant-llm": lambda: ("llm", {"client": FakeClient(compliant)})}
        if a.tracks_live:
            strategies["llm-live"] = lambda: ("llm", {})
        pd.DataFrame(adversarial.run(scenarios, strategies)).to_parquet(out / "track_c.parquet")
        rows = []
        for agg in AGGS:
            for r in misreport.run(scenarios, aggregation=agg):
                rows.append({**r, "aggregation": agg, "costs": json.dumps(r["costs"]), "claims": json.dumps(r["claims"])})
        pd.DataFrame(rows).to_parquet(out / "track_d.parquet")
        print(f"wrote {out / 'track_c.parquet'} and {out / 'track_d.parquet'}")


if __name__ == "__main__":
    main()
