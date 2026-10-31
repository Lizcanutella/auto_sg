"""Build the shareable demo page: site/index.html (self-contained, data embedded).

  python site/build.py

Every number on the page is computed here from results/ and the consensus logs; nothing is typed by hand.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from bench.metrics import boot_ci, over_concession, track_c_summary, track_d_summary  # noqa: E402
from protocol.log import load, verify  # noqa: E402
from sim import evaluate, generate_options, option_by_id  # noqa: E402
from sim.options import fmt_time  # noqa: E402
from tracks.common import load_scenarios  # noqa: E402

RES = ROOT / "results"
EPISODES = [
    ("blocked", "Unsafe move blocked", "Attack on ATC, real row", "A0266", RES / "demo_real_A0266.jsonl"),
    ("live", "Live Claude agents", "Same flight, no attack", "A0266", RES / "demo_real_A0266_live_llm.jsonl"),
    ("denver", "Denver thunderstorms", "Largest saving", "A0238", RES / "logs/A0238__scripted__D2__nash__budget.jsonl"),
    ("ohare", "O'Hare: money left on the table", "Failure: mediator tie-break", "A0381", RES / "logs/A0381__scripted__D2__nash__budget.jsonl"),
    ("ohare-llm", "O'Hare with live Claude, rankings", "Same row, D1", "A0381", RES / "logs/A0381__llm__D1__nash__budget.jsonl"),
    ("gate", "Vetoes only: the wrong gate", "Failure: D0 lacks the planned gate", "A0325", RES / "failure_real_A0325_d0.jsonl"),
    ("nosafe", "No safe plan exists", "System declines", "A0310", RES / "logs/A0310__llm__D2__nash__budget.jsonl"),
]


def clock(m: float) -> str:
    """Destination clock with day rollover: 1572 -> '02:12 +1'."""
    h, mm = divmod(int(round(m)), 60)
    d, h = divmod(h, 24)
    return f"{h:02d}:{mm:02d}" + (f" +{d}" if d else "")


def clean(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def ci(series):
    m, lo, hi = boot_ci(series)
    return {"m": m, "lo": lo, "hi": hi, "n": int(pd.Series(series).notna().sum())}


def plan_card(s, oid):
    if oid is None:
        return None
    e = evaluate(s, option_by_id(generate_options(s), oid))
    tl = e.outcome.timeline
    return {"option": oid, "cost": e.global_cost_usd, "roles": {r: c.total_usd for r, c in e.costs.items()},
            "holding": tl.airborne_holding_min, "ground_delay": tl.ground_delay_min,
            "arrival_delay": tl.arrival_delay_min, "landing": fmt_time(tl.landing_min),
            "in_block": fmt_time(tl.in_block_min), "airport": tl.landing_airport,
            "fuel_kg": e.outcome.pilot.extra_fuel_kg if e.outcome.pilot else None}


def private_brief(s):
    a, p, g = s.atc, s.pilot, s.ground
    pax = sum(c.pax for c in p.connections)
    return {
        "atc": [f"Arrival rate {a.base_aar_per_hour:.0f} → {a.reduced_aar_per_hour:.0f} per hour",
                f"{len(a.arrival_sequence)} other arrivals sequenced",
                f"Holding stack limit {a.max_holding_min:.0f} min",
                "Closed taxiway zones: " + (", ".join(a.closed_taxiway_zones) or "none")],
        "pilot": [f"Fuel on board {p.fuel_on_board_kg:,.0f} kg",
                  f"Holding burn {p.holding_burn_kg_per_min:.0f} kg/min · reserve {p.final_reserve_min:.0f} min",
                  f"{len(p.connections)} connecting flights, {pax} passengers",
                  f"Crew duty ends {clock(p.crew_duty_end_min)}"],
        "ground": [f"Planned gate {g.planned_gate_id}",
                   f"Next leg {g.next_leg.flight_id} at {clock(g.next_leg.sched_departure_min)}" if g.next_leg else "No next leg",
                   f"Ramp shift ends {clock(g.crew_shift_end_min)} · min turnaround {g.min_turnaround_min:.0f} min",
                   f"{len(g.gate_bookings)} other gate bookings"],
    }


def episode(key, title, tag, sid, path, scen, base):
    entries = load(path)
    s = scen[sid]
    f = s.public.focal
    msgs = []
    for e in entries:
        p = e["payload"]
        if e["kind"] in ("mediator", "agent", "invalid", "tampered"):
            veto_n = len(p.get("vetoes") or []) if isinstance(p.get("vetoes"), list) else 0
            msgs.append({"turn": e["turn"], "kind": e["kind"], "sender": e["sender"], "type": p.get("type", "INVALID"),
                         "option": p.get("option_id"), "options": (p.get("option_ids") or [])[:4],
                         "n_options": len(p.get("option_ids") or []), "text": p.get("rationale") or p.get("note") or "",
                         "guard": p.get("guard_notes") or [], "claims": [c["kind"] for c in p.get("claims") or []],
                         "author": p.get("author", ""), "vetoes": veto_n, "hash": e["hash"],
                         "feasible": len(p.get("feasible_ids") or []), "fallback": p.get("fallback_id"),
                         "errors": p.get("errors", [])})
    dec = next((e["payload"] for e in reversed(entries) if e["kind"] == "decision"), None)
    settings = next((e["payload"] for e in entries if e["kind"] == "episode"), {})
    b = base.loc[sid]
    return {
        "key": key, "title": title, "tag": tag, "scenario": sid, "settings": settings,
        "flight": {"id": f"{f.airline}{f.flight_number}", "tail": f.tail_number, "origin": f.origin,
                   "dest": f.destination, "date": f.date, "sched_arr": fmt_time(f.sched_arrival_min),
                   "sched_dep": fmt_time(f.sched_departure_min), "weather_delay": f.recorded_weather_delay_min,
                   "late_aircraft_delay": f.recorded_late_aircraft_delay_min, "arrival_delay": f.recorded_arrival_delay_min,
                   "size": f.size_class.value, "wake": f.wake_category.value},
        "disruption": s.public.weather_summary, "decision_point": s.public.decision_point,
        "n_options": len(generate_options(s)), "private": private_brief(s), "messages": msgs,
        "decision": dec, "chain_ok": verify(entries), "first_hash": entries[0]["hash"], "last_hash": entries[-1]["hash"],
        "plans": {"siloed": plan_card(s, b.siloed), "fcfs": plan_card(s, b.fcfs), "best": plan_card(s, b.best),
                  "negotiated": plan_card(s, dec.get("option_id")) if dec else None},
    }


def main():
    d = pd.read_parquet(RES / "results.parquet")
    scen = {s.scenario_id: s for s in load_scenarios(str(ROOT / "data/scenarios.jsonl"))}
    base = d[d.system.isin(["siloed", "fcfs", "best_possible"])].pivot(index="scenario_id", columns="system", values="option_id")
    base.columns = [c.replace("best_possible", "best") for c in base.columns]

    neg = d[d.system.isin(["scripted", "llm"])]
    chart = []
    for (system, acc, lvl, agg), g in neg.groupby(["system", "acceptance", "disclosure", "aggregation"]):
        chart.append({"system": system, "acceptance": acc, "level": lvl, "agg": agg, **ci(g.gap_closed),
                      "fcfs": ci(g.gap_closed_fcfs)})
    sil = d[d.system == "siloed"]
    fc = d[d.system == "fcfs"]
    solv = sil[sil.status != "ESCALATE"]
    budget = neg[(neg.system == "scripted") & (neg.acceptance == "budget")]

    # per-flight impact, D2 Nash vs siloed
    imp = {"hold_sil": 0, "hold_neg": 0, "fuel_sil": 0, "fuel_neg": 0, "cost_sil": 0, "cost_neg": 0}
    rows = budget[(budget.disclosure == "D2") & (budget.aggregation == "nash") & (budget.status != "ESCALATE")]
    for _, r in rows.iterrows():
        s = scen[r.scenario_id]
        for k, oid in (("sil", base.loc[r.scenario_id].siloed), ("neg", r.option_id)):
            c = plan_card(s, oid)
            imp[f"hold_{k}"] += c["holding"]
            imp[f"fuel_{k}"] += c["fuel_kg"] or 0
            imp[f"cost_{k}"] += c["cost"]
    n = len(rows)
    impact = {k: v / n for k, v in imp.items()} | {"n": n}

    llm = neg[neg.system == "llm"]
    claims = {"pilot": 0, "ground": 0, "atc": 0, "accepted": 0}
    for p in (RES / "logs").glob("*__llm__*.jsonl"):
        for e in load(p):
            if e["kind"] == "mediator" and e["payload"].get("type") == "CLAIM":
                note = e["payload"]["note"]
                claims[note.split()[0]] = claims.get(note.split()[0], 0) + 1
                claims["accepted"] += "ACCEPTED" in note
    oc = over_concession(d)
    tc = track_c_summary(pd.read_parquet(RES / "track_c.parquet"))
    td = track_d_summary(pd.read_parquet(RES / "track_d.parquet"))
    sens = pd.read_parquet(RES / "sensitivity.parquet")
    sens = sens[sens.system == "scripted"].groupby(["weighting", "disclosure"]).gap_closed.mean().unstack()

    worst = budget[budget.gap_closed < -1e-6]
    board = []
    for sid in ("A0238", "A0199", "A0458", "A0266"):
        s, r = scen[sid], budget[(budget.scenario_id == sid) & (budget.disclosure == "D2") & (budget.aggregation == "nash")].iloc[0]
        sp, np_ = plan_card(s, base.loc[sid].siloed), plan_card(s, r.option_id)
        board.append({"flight": f"{s.public.focal.airline}{s.public.focal.flight_number}",
                      "route": f"{s.public.focal.origin}-{s.public.focal.destination}", "date": s.public.focal.date,
                      "today": f"{'HOLD ' + str(round(sp['holding'])) + 'M' if sp['holding'] > 0.5 else 'GATE ' + sp['option'].split('/')[-1]}",
                      "today_cost": sp["cost"], "agreed": f"{'GND DLY' if np_['ground_delay'] > 0.5 else 'ON TIME'} {clock(evaluate(s, option_by_id(generate_options(s), r.option_id)).outcome.timeline.landing_min)[:5]}",
                      "agreed_cost": np_["cost"], "saved": sp["cost"] - np_["cost"]})

    data = {
        "episodes": [episode(*e, scen, base) for e in EPISODES],
        "chart": chart, "board": board, "impact": impact,
        "headline": {
            "scenarios": int(d.scenario_id.nunique()), "solvable": int(len(solv)),
            "no_safe": int((sil.status == "ESCALATE").sum()), "with_gap": int(sil.gap_closed.notna().sum()),
            "fcfs_gap": ci(fc.gap_closed), "episodes": int(len(neg)), "violations": int(neg.violations.sum()),
            "correct_escalation": float(neg.correct_escalation.mean()),
            "scripted_episodes": int((neg.system == "scripted").sum()), "llm_episodes": int(len(llm)),
            "max_turns": int(neg.turns.max()), "worse_than_siloed": int(len(worst)),
            "worse_cases_levels": sorted(worst.disclosure.unique().tolist()),
            "budget_by_level": {lvl: ci(g.gap_closed) for lvl, g in budget.groupby("disclosure")},
        },
        "llm": {"episodes": int(len(llm)), "calls": int(llm.llm_calls.sum()), "moves": int(llm.llm_moves.sum()),
                "fallbacks": int(llm.llm_fallbacks.sum()), "unsupported": int(llm.llm_unsupported_numbers.sum()),
                "attempted_unsafe": int(llm.llm_attempted_unsafe.sum()), "tool_calls": int(llm.llm_tool_calls.sum()),
                "violations": int(llm.violations.sum()), "status": llm.status.value_counts().to_dict(),
                "tokens": float((llm.llm_input_tokens + llm.llm_output_tokens).mean()),
                "usd": float(((llm.llm_input_tokens * 0.10 + llm.llm_output_tokens * 0.50) / 1e6).mean()),
                "latency": float(llm.llm_latency_s.mean()), "claims": claims,
                "same_plan": float(oc.same_plan.iloc[0]) if len(oc) else None, "pairs": int(oc.pairs.iloc[0]) if len(oc) else 0,
                "gave_up": {r.role: r.gave_up_usd[0] for r in oc.itertuples()} if len(oc) else {}},
        "track_c": [{"strategy": r.strategy, "cases": r.cases, "followed": r.injection_followed[0],
                     "blocks": r.guard_blocks, "unsafe_final": r.final_plan_is_unsafe_option,
                     "violations": r.final_violations} for r in tc.itertuples()],
        "track_d": td.to_dict(orient="records"),
        "sensitivity": {w: sens.loc[w].to_dict() for w in ["default", "passengers first", "fuel x2", "ATC weight x3"] if w in sens.index},
    }
    html = (ROOT / "site/template.html").read_text().replace("/*__DATA__*/null", json.dumps(clean(data), default=str))
    (ROOT / "site/index.html").write_text(html)
    print(f"wrote site/index.html ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
