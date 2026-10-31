"""Simulator validity check (A-8): does our knock-on delay model match what really happened?

Our simulator (sim/simulate.py, ground_outcome) predicts the next leg of the same aircraft as
    next_leg_delay = max(0, in_block + min_turnaround - next_leg_sched_departure)
Here we feed it each flight's RECORDED arrival delay and compare the prediction with the next
leg's RECORDED delay, over every pair in flights.csv (not just the 500 sampled scenarios).

Selection bias: flights.csv only holds delayed flights, so a next leg is in the file only if it was
itself delayed (LATE_AIRCRAFT_DELAY > 20 or WEATHER_DELAY > 15). Small observed delays are cut off,
so predictions below ~20 min are compared against an upward-biased sample. `predicted >= 20` is
the fairer subset.

  python -m bench.sim_validity      -> results/sim_validity.md, results/charts/sim_validity.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bench.charts import GRID, INK, INK_2, SERIES, SURFACE, _style  # noqa: E402
from scenarios.flights import load_flights  # noqa: E402
from scenarios.workbook import load_workbook  # noqa: E402

OUT = Path("results")
NEXT_LEG_WINDOW_MIN = 720      # same rule as scenarios/build.py: next leg within 12 h of scheduled arrival
FILE_THRESHOLD_MIN = 20        # a leg enters flights.csv with LATE_AIRCRAFT_DELAY > 20 (or weather > 15)
TIGHT_SLACK_MIN = 15           # scheduled ground time minus minimum turnaround <= this -> "tight"


def pairs(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every flight whose same-tail next leg (departing from its destination within 12 h) is in the file,
    with the model's predicted knock-on delay and the next leg's recorded delays."""
    df = load_flights() if df is None else df
    wb = load_workbook()
    left = df[["flight_id", "TAIL_NUMBER", "DESTINATION_AIRPORT", "sched_arr_abs", "ARRIVAL_DELAY"]]
    left = left.sort_values("sched_arr_abs")
    right = df[["flight_id", "TAIL_NUMBER", "ORIGIN_AIRPORT", "sched_dep_abs_origin",
                "LATE_AIRCRAFT_DELAY", "DEPARTURE_DELAY", "WEATHER_DELAY"]].rename(columns={
        "flight_id": "next_flight_id", "ORIGIN_AIRPORT": "DESTINATION_AIRPORT",
        "sched_dep_abs_origin": "next_sched_dep_abs", "LATE_AIRCRAFT_DELAY": "next_late_aircraft_delay",
        "DEPARTURE_DELAY": "next_departure_delay", "WEATHER_DELAY": "next_weather_delay"})
    right = right.sort_values("next_sched_dep_abs")
    # First leg of the same tail leaving our destination strictly after our scheduled arrival.
    m = pd.merge_asof(left, right, left_on="sched_arr_abs", right_on="next_sched_dep_abs",
                      by=["TAIL_NUMBER", "DESTINATION_AIRPORT"], direction="forward",
                      allow_exact_matches=False, tolerance=NEXT_LEG_WINDOW_MIN - 1)
    m = m.dropna(subset=["next_flight_id"]).copy()
    m["size_class"] = m.DESTINATION_AIRPORT.map(lambda a: wb.airports[a].size_class)
    m["min_turnaround_min"] = m.DESTINATION_AIRPORT.map(lambda a: wb.airports[a].min_turnaround_min)
    in_block = m.sched_arr_abs + m.ARRIVAL_DELAY
    m["predicted_min"] = (in_block + m.min_turnaround_min - m.next_sched_dep_abs).clip(lower=0)
    m["slack_min"] = m.next_sched_dep_abs - m.sched_arr_abs - m.min_turnaround_min
    m["tight_slack"] = m.slack_min <= TIGHT_SLACK_MIN
    return m.reset_index(drop=True)


def score(pred: pd.Series, obs: pd.Series) -> dict:
    err = pred - obs
    return {"N": len(err), "MAE": err.abs().mean(), "median_abs_err": err.abs().median(),
            "bias": err.mean(), "pearson": pred.corr(obs), "spearman": pred.rank().corr(obs.rank()),
            "within_15": (err.abs() <= 15).mean()}


def breakdown(p: pd.DataFrame, obs_col: str = "next_late_aircraft_delay") -> pd.DataFrame:
    groups = [("all pairs", p), ("predicted >= 20 min", p[p.predicted_min >= FILE_THRESHOLD_MIN]),
              ("predicted < 20 min", p[p.predicted_min < FILE_THRESHOLD_MIN]),
              ("tight slack (<= 15 min spare)", p[p.tight_slack]), ("loose slack (> 15 min spare)", p[~p.tight_slack])]
    groups += [(f"{c}", g) for c, g in p.groupby("size_class")]
    return pd.DataFrame([{"subset": name, **score(g.predicted_min, g[obs_col])} for name, g in groups if len(g) > 1])


def chart(p: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lim = 300
    q = p[(p.predicted_min <= lim) & (p.next_late_aircraft_delay <= lim)]
    fig, ax = plt.subplots(figsize=(6.4, 5.6), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    hb = ax.hexbin(q.predicted_min, q.next_late_aircraft_delay, gridsize=50, bins="log", cmap="Blues", mincnt=1)
    ax.plot([0, lim], [0, lim], color=INK, linewidth=1, linestyle="--", label="perfect prediction (y = x)")
    bins = np.arange(0, lim + 20, 20)
    mid = q.groupby(pd.cut(q.predicted_min, bins), observed=True).next_late_aircraft_delay.median()
    ax.plot([b.mid for b in mid.index], mid.values, color=SERIES[1], linewidth=2, marker="o", markersize=3,
            label="median recorded, per 20-min bin")
    ax.axhline(FILE_THRESHOLD_MIN, color=INK_2, linewidth=0.8, linestyle=":")
    ax.text(lim * 0.98, FILE_THRESHOLD_MIN + 4, "file only holds > 20 min", ha="right", color=INK_2, fontsize=8)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Predicted knock-on delay of next leg (min)", color=INK_2)
    ax.set_ylabel("Recorded LATE_AIRCRAFT_DELAY of next leg (min)", color=INK_2)
    ax.set_title(f"Knock-on delay model vs recorded outcome ({len(p):,} real pairs)", color=INK, fontsize=11,
                 loc="left")
    fig.colorbar(hb, ax=ax, label="pairs (log scale)")
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def implied_turnaround(p: pd.DataFrame) -> pd.Series:
    """Turnaround the recorded knock-on delay implies: next delay + next scheduled departure - actual in-block."""
    return p.next_late_aircraft_delay + p.next_sched_dep_abs - (p.sched_arr_abs + p.ARRIVAL_DELAY)


def to_markdown(p: pd.DataFrame, n_rows: int) -> str:
    t = breakdown(p)
    dep = score(p.predicted_min, p.next_departure_delay)
    fair = t.set_index("subset").loc["predicted >= 20 min"]
    small = t.set_index("subset").loc["predicted < 20 min"]
    fmt = t.assign(MAE=t.MAE.map("{:.1f}".format), median_abs_err=t.median_abs_err.map("{:.1f}".format),
                   bias=t.bias.map("{:+.1f}".format), pearson=t.pearson.map("{:.2f}".format),
                   spearman=t.spearman.map("{:.2f}".format), within_15=t.within_15.map("{:.0%}".format),
                   N=t.N.map("{:,}".format))
    absorbed = (p.predicted_min == 0).mean()
    q = p[p.predicted_min >= FILE_THRESHOLD_MIN]
    turn = q.assign(implied=implied_turnaround(q)).groupby("size_class").agg(
        implied=("implied", "median"), workbook=("min_turnaround_min", "first"))
    turn_txt = "; ".join(f"{c}: {r.implied:.0f} vs {r.workbook:.0f}" for c, r in turn.iterrows())
    direction = ("over-predicts" if fair.bias > 0 else "under-predicts")
    lines = [
        "# Simulator validity check (A-8)\n",
        "Our knock-on model: next-leg delay = max(0, actual in-block + workbook min turnaround − next leg's "
        "scheduled departure). Fed each flight's **recorded** arrival delay and compared with the next leg's "
        f"**recorded** `LATE_AIRCRAFT_DELAY`. Pairs: every flight in `flights.csv` whose same-tail next leg "
        f"(from its destination, within 12 h) is also in the file: **{len(p):,} of {n_rows:,} rows "
        f"({len(p) / n_rows:.0%})**. Errors are predicted − recorded, in minutes.\n",
        fmt.rename(columns={"median_abs_err": "median |err|", "within_15": "within ±15 min"}).to_markdown(index=False),
        f"\nSecondary target (next leg's total `DEPARTURE_DELAY`, all pairs): MAE {dep['MAE']:.1f}, "
        f"bias {dep['bias']:+.1f}, Pearson {dep['pearson']:.2f}.\n",
        "## Findings\n",
        f"- **On the fairer subset (predicted ≥ 20 min, N = {int(fair.N):,})** the model is off by {fair.MAE:.0f} min "
        f"on average (median {fair.median_abs_err:.0f}), with bias {fair.bias:+.0f} min, Pearson {fair.pearson:.2f} "
        f"and Spearman {fair.spearman:.2f}; {fair.within_15:.0%} of predictions land within ±15 min.",
        f"- **The model {direction} knock-on delay because the workbook's minimum turnaround is longer than what "
        f"late aircraft actually achieve.** Median turnaround implied by the recorded delays vs workbook minimum "
        f"(min): {turn_txt}. Airlines compress turns when running late (regional carriers ~24 min). So the ground "
        f"agent's `knock_on_delay` cost is an upper bound: it overstates what arriving late costs downstream. "
        f"We keep the workbook value (organiser rule) and state this.",
        "- **The correlation is high partly by construction.** BTS records `LATE_AIRCRAFT_DELAY` as delay caused "
        "by the previous flight of the same aircraft arriving late, which is what the model computes. So this "
        "checks our turnaround arithmetic and its parameter, not an independent causal claim.",
        f"- **Selection bias: small predictions cannot be scored fairly.** A next leg is only in the file if it was "
        f"itself delayed (> 20 min late-aircraft, or weather). When we predict < 20 min (N = {int(small.N):,}; "
        f"{absorbed:.0%} of all pairs predict exactly 0) we only see the next legs that stayed late, so that "
        f"subset's bias ({small.bias:+.0f} min) is an artefact. The {1 - len(p) / n_rows:.0%} of flights whose next "
        "leg is not in the file are mostly delays that were absorbed, the cases the model would get right; they "
        "cannot be scored with this extract.",
    ]
    return "\n".join(lines) + "\n"


def main():
    df = load_flights()
    p = pairs(df)
    OUT.mkdir(exist_ok=True)
    md = to_markdown(p, len(df))
    (OUT / "sim_validity.md").write_text(md)
    chart(p, OUT / "charts" / "sim_validity.png")
    print(md)
    print(f"wrote {OUT / 'sim_validity.md'} and {OUT / 'charts' / 'sim_validity.png'}")


if __name__ == "__main__":
    main()
