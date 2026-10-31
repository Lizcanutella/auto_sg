"""Workstream D smoke tests: benchmark runner, metrics, charts, UI."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from bench import charts, metrics
from bench.run import run
from tracks.common import load_scenarios


def test_benchmark_metrics_and_chart(tmp_path):
    df = run(load_scenarios(), levels=["D0", "D3"], aggs=["weighted_sum"], out=tmp_path, workers=1)
    df.to_parquet(tmp_path / "results.parquet")
    neg = df[df.system == "scripted"]
    assert len(neg) == 6 and neg.violations.sum() == 0
    assert set(df.system) == {"siloed", "fcfs", "best_possible", "scripted"}
    ep1 = neg[(neg.scenario_id == "episode_001") & (neg.disclosure == "D3")].iloc[0]
    assert ep1.gap_closed == 1.0 and ep1.gap_closed_fcfs == 1.0     # all data shared: reaches the best plan
    md = metrics.to_markdown(tmp_path)
    assert "Negotiation" in md and "| scripted | D3 | weighted_sum |" in md
    assert charts.key_chart(tmp_path).exists()
    again = run(load_scenarios(), levels=["D0", "D3"], aggs=["weighted_sum"], out=tmp_path, workers=1)
    pd.testing.assert_series_equal(again.sort_values(["scenario_id", "system", "disclosure"]).global_cost_usd.reset_index(drop=True),
                                   df.sort_values(["scenario_id", "system", "disclosure"]).global_cost_usd.reset_index(drop=True))


def test_bootstrap_ci_brackets_the_mean():
    m, lo, hi = metrics.boot_ci([0, 1, 1, 0, 1])
    assert lo <= m <= hi


def test_ui_runs_a_negotiation_and_records_approval():
    from streamlit.testing.v1 import AppTest
    # Absolute path: newer Streamlit resolves relative paths against this test file, not the repo root.
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "ui" / "app.py"), default_timeout=120).run()
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any("CONSENSUS" in s.value for s in at.success)
    next(b for b in at.button if b.label == "Approve").click().run()
    assert any("APPROVE" in i.value for i in at.info)
