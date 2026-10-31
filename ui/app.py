"""Duty-manager UI (D-4).   streamlit run ui/app.py

Negotiation tab: run a scenario or replay any consensus log; turn-by-turn timeline; rule chips
(pass/fail with value, limit and source); final plan vs today's process and the best possible;
Approve / Override, appended to the same hash-chained log.
Results tab: benchmark tables and charts from results/.
Everything on the Negotiation tab is rendered from the log entries, so any logged episode replays.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from contracts import Scenario  # noqa: E402
from protocol import log as clog  # noqa: E402
from protocol import run_episode  # noqa: E402
from protocol.log import ConsensusLog  # noqa: E402

st.set_page_config(page_title="Disruption negotiation", layout="wide")
TYPE_ICON = {"PROPOSE": "📨", "ACCEPT": "✅", "COUNTER": "↩️", "REJECT": "⛔", "ESCALATE": "🚨",
             "BROADCAST": "📢", "PROPOSAL": "🗂️", "FINAL": "🏁", "CLAIM": "⚖️"}
ROLE_NAME = {"mediator": "Mediator", "atc": "ATC", "pilot": "Airline / pilot", "ground": "Ground handler"}


def scenario_files() -> list[Path]:
    return sorted((ROOT / "fixtures").glob("episode_*.json")) + sorted((ROOT / "data").glob("*.jsonl"))


def load_scenario(path: Path, index: int) -> Scenario:
    if path.suffix == ".jsonl":
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        return Scenario.model_validate_json(lines[index])
    return Scenario.model_validate_json(path.read_text())


def log_files() -> list[Path]:
    files = list((ROOT / "results" / "logs").glob("*.jsonl")) + list((ROOT / "runs").glob("*.jsonl"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def parse_option(oid: str | None) -> str:
    if not oid:
        return "no plan"
    if oid.endswith("/divert"):
        return f"**Divert** ({oid.split('/')[0]})"
    route_slot, absorption, gate = oid.split("/")
    route, slot = route_slot.split("@")
    return f"Land **{slot}** · route **{route}** · delay taken **{absorption}** · gate **{gate}**"


# ------------------------------------------------------------------ sidebar
st.sidebar.title("Episode")
mode = st.sidebar.radio("Source", ["Run a scenario", "Replay a log"])
if mode == "Run a scenario":
    files = scenario_files()
    f = Path(st.sidebar.selectbox("Scenario file", [str(x) for x in files], format_func=lambda x: Path(x).name))
    idx = st.sidebar.number_input("Index (for .jsonl)", 0, 100000, 0) if f.suffix == ".jsonl" else 0
    level = st.sidebar.selectbox("Disclosure level", ["D0", "D1", "D2", "D3"], index=2,
                                 help="D0 veto only · D1 ranking · D2 scores · D3 all private data")
    agg = st.sidebar.selectbox("Aggregation rule", ["nash", "weighted_sum", "maxmin"])
    acc = st.sidebar.selectbox("Acceptance policy", ["budget", "rational", "cooperative"])
    agents = st.sidebar.selectbox("Agents", ["scripted", "llm"])
    if st.sidebar.button("Run negotiation", type="primary"):
        scn = load_scenario(f, int(idx))
        with st.spinner("Negotiating..."):
            res = run_episode(scn, strategy=agents, disclosure=level, aggregation=agg, acceptance=acc)
        path = ROOT / "runs" / f"ui_{scn.scenario_id}_{int(time.time())}.jsonl"
        res.log.write(path)
        st.session_state.update(log_path=str(path), scenario=scn)
else:
    logs = log_files()
    if logs:
        p = st.sidebar.selectbox("Log", [str(x) for x in logs], format_func=lambda x: Path(x).name)
        if st.sidebar.button("Load", type="primary"):
            st.session_state.update(log_path=str(p), scenario=None)
    else:
        st.sidebar.info("No logs yet: run `python -m bench.run` or a scenario.")

tab_neg, tab_res = st.tabs(["Negotiation", "Results"])

# ------------------------------------------------------------------ negotiation tab
with tab_neg:
    if "log_path" not in st.session_state:
        st.info("Run a scenario or load a log from the sidebar.")
    else:
        path = Path(st.session_state.log_path)
        entries = clog.load(path)
        rep = clog.replay(entries)
        s = rep["settings"]
        st.subheader(f"Scenario {rep['scenario_id']}")
        st.caption(f"Disclosure {s.get('disclosure')} · aggregation {s.get('aggregation')} · acceptance "
                   f"{s.get('acceptance')} · agents {s.get('strategies')} · log `{path.name}` · hash chain "
                   f"{'verified ✅' if rep['chain_ok'] else 'BROKEN ❌'}")
        scn = st.session_state.get("scenario")
        if scn is not None:
            fo = scn.public.focal
            st.markdown(f"**{fo.airline}{fo.flight_number}** {fo.origin} → {fo.destination} · {fo.date} · "
                        f"decision {scn.public.decision_point} · _{scn.public.weather_summary}_")
            prov = sorted({v.value for v in scn.provenance.values()}) if scn.provenance else []
            if prov:
                st.caption("Data provenance in this scenario: " + ", ".join(prov))

        for turn in sorted({e["turn"] for e in entries if e["kind"] in ("mediator", "agent", "invalid", "tampered")}):
            st.markdown(f"#### Turn {turn}")
            cols = st.columns(4)
            for col, who in zip(cols, ["mediator", "atc", "pilot", "ground"]):
                with col:
                    st.markdown(f"**{ROLE_NAME[who]}**")
                    for e in entries:
                        if e["turn"] != turn:
                            continue
                        p = e["payload"]
                        if e["kind"] == "invalid" and e["sender"] == who:
                            st.error("Invalid message → treated as REJECT\n\n" + "\n".join(p["errors"]))
                        elif e["kind"] == "tampered" and e["sender"].endswith(who):
                            st.warning(f"⚠️ Message to {who} was tampered with (adversarial test)")
                        elif e["sender"] == who and e["kind"] in ("mediator", "agent"):
                            t = p.get("type", "")
                            with st.container(border=True):
                                st.markdown(f"{TYPE_ICON.get(t, '•')} **{t}** "
                                            + (f"`{p['option_id']}`" if p.get("option_id") else ""))
                                if t in ("PROPOSAL", "FINAL") and p.get("option_ids"):
                                    st.markdown("\n".join(f"- `{o}`" for o in p["option_ids"]))
                                text = p.get("rationale") or p.get("note") or ""
                                if text:
                                    st.caption(text)
                                if p.get("vetoes"):
                                    st.caption(f"Vetoed {len(p['vetoes'])} options (own hard rules)")
                                for c in p.get("claims", []):
                                    st.caption(f"Claim: {c['kind']}")
                                for n in p.get("guard_notes", []):
                                    st.warning("Guard: " + n)
                                if p.get("author", "").startswith("llm"):
                                    st.caption(f"by {p['author']}")

        d = rep["decision"]
        st.divider()
        if d:
            if d["status"] == "ESCALATE":
                st.error(f"🚨 **No safe plan found** after {d['turns']} turn(s): {d['reason']}. "
                         "The system makes no recommendation; the duty manager decides.")
                if d.get("vetoes"):
                    st.write("Vetoes by rule:", d["vetoes"])
            else:
                (st.success if d["status"] == "CONSENSUS" else st.warning)(
                    f"**{d['status']}** after {d['turns']} turn(s): {d['reason']}")
                st.markdown("### Recommended plan\n" + parse_option(d["option_id"]))
                if d["status"] == "FALLBACK":
                    st.caption("No unanimity within 3 turns: the deterministic standard procedure was imposed.")
                st.markdown("**Rule check of this plan (each organisation's own checker)**")
                for role, rules in d.get("evidence", {}).items():
                    chips = []
                    for r in rules:
                        ok = "✅" if r["passed"] else "❌"
                        val = "" if r.get("value") is None else f" {r['value']}{(' / ' + str(r['limit'])) if r.get('limit') is not None else ''} {r.get('unit', '')}"
                        chips.append(f"{ok} `{r['rule_id']}`{val}")
                    st.markdown(f"**{ROLE_NAME[role]}:** " + " · ".join(chips))
                    with st.expander(f"Sources for {ROLE_NAME[role]} rules"):
                        st.table(pd.DataFrame([{k: r.get(k) for k in ("rule_id", "passed", "value", "limit", "unit",
                                                                    "source", "detail")} for r in rules]))
                if scn is not None:
                    from baselines import best_possible, fcfs_rbs
                    from sim import evaluate, generate_options, option_by_id
                    rows = []
                    for name, oid in [("Negotiated", d["option_id"]),
                                      ("Today's process (FCFS/RBS)", getattr(fcfs_rbs.plan(scn).chosen, "option", None)),
                                      ("Best possible (all data)", getattr(best_possible.plan(scn).chosen, "option", None))]:
                        if oid is None:
                            continue
                        oid = oid if isinstance(oid, str) else oid.option_id
                        ev = evaluate(scn, option_by_id(generate_options(scn), oid))
                        rows.append({"plan": name, "option": oid, "global cost (USD)": round(ev.global_cost_usd),
                                     **{f"{r} (USD)": round(c.total_usd) for r, c in ev.costs.items()},
                                     "arrival delay (min)": round(ev.outcome.timeline.arrival_delay_min)})
                    st.markdown("**Compared with today's process and the best possible plan** "
                                "(computed after the fact with all data; never used in the negotiation)")
                    st.dataframe(pd.DataFrame(rows), hide_index=True)

            st.markdown("### Duty manager")
            if rep["human"]:
                h = rep["human"]
                st.info(f"Recorded: **{h['decision']}** {h['option_id'] or ''} {h['note']}")
            else:
                note = st.text_input("Note (optional)")
                feasible = next((e["payload"].get("feasible_ids") for e in entries
                                 if e["kind"] == "mediator" and e["payload"].get("feasible_ids")), []) or []
                c1, c2 = st.columns([1, 2])
                approve = c1.button("Approve", type="primary", disabled=d["status"] == "ESCALATE")
                override_to = c2.selectbox("Override with (options nobody vetoed)", [""] + feasible)
                override = c2.button("Override", disabled=not override_to)
                if approve or override:
                    log = ConsensusLog(rep["scenario_id"], entries=entries)
                    if approve:
                        log.human("APPROVE", d["option_id"], note)
                    else:
                        log.human("OVERRIDE", override_to, note)
                    log.write(path)
                    st.rerun()

# ------------------------------------------------------------------ results tab
with tab_res:
    res_dir = ROOT / "results"
    if not (res_dir / "results.parquet").exists():
        st.info("No benchmark yet: run `python -m bench.run --tracks && python -m bench.metrics && python -m bench.charts`.")
    else:
        for png in ("gap_vs_disclosure.png", "sensitivity.png"):
            f = res_dir / "charts" / png
            if f.exists():
                st.image(str(f))
        for md in ("metrics.md", "sensitivity.md"):
            f = res_dir / md
            if f.exists():
                st.markdown(f.read_text())
        with st.expander("Raw results table"):
            st.dataframe(pd.read_parquet(res_dir / "results.parquet"))
