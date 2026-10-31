"""Charts (D-3) and cost-weight sensitivity (D-7).

  python -m bench.charts                 # key chart from results/results.parquet
  python -m bench.charts --sensitivity   # also re-run scripted agents under 4 cost weightings

Static PNGs for the slides; the same numbers are in results/metrics.md (the table view).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from bench.metrics import boot_ci  # noqa: E402
from sim.params import DEFAULT_COSTS  # noqa: E402

LEVELS = ["D0", "D1", "D2", "D3"]
LEVEL_LABELS = {"D0": "D0\nveto only", "D1": "D1\nranking", "D2": "D2\nscores", "D3": "D3\nall data"}
AGGS = ["weighted_sum", "maxmin", "nash"]
AGG_TITLES = {"weighted_sum": "Weighted sum", "maxmin": "Max-min fairness", "nash": "Nash bargaining"}
# reference categorical palette, fixed order (dataviz skill references/palette.md, light mode)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

SENSITIVITY = {
    "default": {},
    "passengers first": {"missed_connection_usd_per_pax": 500.0, "delay_usd_per_min": 75.0},
    "fuel x2": {"fuel_usd_per_kg": 1.60},
    "ATC weight x3": {"weight_atc": 3.0},
}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _series(df: pd.DataFrame, agg: str, label_col: str, label) -> tuple[list, list, list]:
    m, lo, hi = [], [], []
    for lvl in LEVELS:
        g = df[(df.aggregation == agg) & (df.disclosure == lvl) & (df[label_col] == label)].gap_closed
        mean, l, h = boot_ci(g)
        m.append(mean)
        lo.append(mean if pd.isna(l) else l)
        hi.append(mean if pd.isna(h) else h)
    return m, lo, hi


def gap_chart(df: pd.DataFrame, path: Path, label_col: str, labels: list, title: str, subtitle: str):
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True, facecolor=SURFACE)
    base_x = list(range(len(LEVELS)))
    for ax, agg in zip(axes, AGGS):
        _style(ax)
        placed: list[float] = []                       # label y positions already used (collision avoidance)
        for i, lab in enumerate(labels):
            m, lo, hi = _series(df, agg, label_col, lab)
            if all(pd.isna(v) for v in m):
                continue
            c = SERIES[i]
            dx = (i - (len(labels) - 1) / 2) * 0.07    # small dodge so identical series stay visible
            x = [v + dx for v in base_x]
            ax.fill_between(x, lo, hi, color=c, alpha=0.12, linewidth=0)
            ax.plot(x, m, color=c, linewidth=2, marker="o", markersize=6,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, label=str(lab))
            last = max(j for j, v in enumerate(m) if not pd.isna(v))
            if len(labels) <= 4 and ax is axes[-1]:
                y = m[last]
                while any(abs(y - q) < 0.07 for q in placed):
                    y -= 0.08
                placed.append(y)
                ax.annotate(str(lab), (base_x[-1] + 0.15, y), xytext=(4, 0), textcoords="offset points",
                            va="center", fontsize=9, color=INK_2, annotation_clip=False)
        ax.set_title(AGG_TITLES[agg], fontsize=10, color=INK, loc="left")
        ax.set_xticks(base_x, [LEVEL_LABELS[lv] for lv in LEVELS])
        ax.set_ylim(-0.05, 1.08)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"])
        ax.axhline(0, color=INK_2, linewidth=0.8)
    axes[0].set_ylabel("Gap closed\n(0% = FCFS, 100% = best possible)", fontsize=9, color=INK_2)
    handles, labs = axes[0].get_legend_handles_labels()
    if not handles:
        for ax in axes[1:]:
            handles, labs = ax.get_legend_handles_labels()
            if handles:
                break
    if len(handles) >= 2:
        fig.legend(handles, labs, loc="upper right", frameon=False, fontsize=9, ncol=len(handles),
                   bbox_to_anchor=(0.99, 1.0), labelcolor=INK_2)
    fig.suptitle(title, x=0.01, ha="left", fontsize=12, color=INK, y=1.0)
    fig.text(0.01, 0.91, subtitle, fontsize=9, color=INK_2, ha="left")
    fig.tight_layout(rect=(0, 0, 0.97, 0.9))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path


def key_chart(results: Path, acceptance: str = "budget") -> Path:
    df = pd.read_parquet(results / "results.parquet")
    df = df[df.system.isin(["scripted", "llm"]) & (df.acceptance == acceptance)]
    n = df[df.gap_closed.notna()].scenario_id.nunique()
    labels = [s for s in ("scripted", "llm") if s in set(df.system)]
    sub = (f"{n} scenario(s) with a gap to close; bands = 95% bootstrap CI; acceptance policy: {acceptance}"
           + ("" if "llm" in labels else "; LLM agents not run yet"))
    return gap_chart(df, results / "charts" / "gap_vs_disclosure.png", "system", labels,
                     "How much does each organisation need to share?", sub)


def sensitivity(scenarios, results: Path) -> tuple[Path, pd.DataFrame]:
    from bench.run import run
    frames = []
    for name, overrides in SENSITIVITY.items():
        p = DEFAULT_COSTS.model_copy(update=overrides)
        d = run(scenarios, params=p, out=results / "sensitivity" / name.replace(" ", "_"), label=name)
        d["weighting"] = name
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(results / "sensitivity.parquet")
    neg = df[df.system == "scripted"]
    head = (neg.groupby(["weighting", "disclosure"]).gap_closed.mean().unstack().reindex(list(SENSITIVITY))
            .map(lambda v: "–" if pd.isna(v) else f"{v:.0%}"))
    n = neg[neg.gap_closed.notna()].groupby("weighting").scenario_id.nunique().to_dict()
    counts = sorted(set(n.values()))
    sub = (f"scripted agents, bounded concession; {', '.join(map(str, counts))} scenario(s) with a gap to close"
           " per weighting; series nudged sideways so overlapping lines stay visible")
    path = gap_chart(neg, results / "charts" / "sensitivity.png", "weighting", list(SENSITIVITY),
                     "Do the conclusions survive different cost weights?", sub)
    return path, head


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--scenarios")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    res = Path(a.results)
    print("wrote", key_chart(res))
    if a.sensitivity:
        from tracks.common import load_scenarios
        path, head = sensitivity(load_scenarios(a.scenarios, a.limit), res)
        md = "## Sensitivity: mean gap closed (scripted, all aggregation rules)\n\n" + head.to_markdown() + "\n"
        (res / "sensitivity.md").write_text(md)
        print("wrote", path)
        print(md)


if __name__ == "__main__":
    main()
