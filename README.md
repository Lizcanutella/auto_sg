# The Price of Silos

**Airbus Track, Challenge #2 · Autonomous SG 2026.** Three AI agents, for air traffic control, the airline/pilot and the ground handler, negotiate how to handle a disrupted flight: revised arrival time, gate and flight plan. They do it in at most 3 turns, and each agent sees only its own organisation's data. A deterministic mediator runs the protocol, rule checkers enforce safety, and a duty manager approves the result.

We also ask the question the A-CDM and UDPP debates ask: **how much does each organisation need to share to get most of the benefit?** Our benchmark compares the negotiated plan with today's first-come-first-served process and with a solver that sees everyone's data.

## User and status quo
- **User:** the airline hub duty manager, working with the approach-control traffic manager and ramp/gate control.
- **Today:** when weather cuts the arrival rate, the FAA assigns slots by Ration-by-Schedule (first-come-first-served). Gate, crew and connection fixes then happen over the phone and on manual gate boards. That costs delay minutes, holding fuel and missed connections.

## How it works

```
DOT row ──► scenario (public part + one private part per organisation)
             │
             ├─ ATC agent     ─┐  each agent: own view only; own rule checker (veto + rule ID + source);
             ├─ Pilot agent   ─┼─ own private cost; strategy = scripted or LLM (one Claude call per move)
             ├─ Ground agent  ─┘  guard: can never propose/accept an option its own rules reject
             ▼
        Mediator (deterministic, public data only)
        T1 vetoes + preferences → T2 top-k proposal → accept / counter → T3 final → consensus
        | otherwise fallback (Ration-by-Schedule + first-fit gate among options nobody vetoed)
        | no safe option → ESCALATE
             ▼
        Final safety gate (every agent re-checks the plan) → hash-chained log → duty manager
```

| Job | Done by | LLM? |
|---|---|---|
| Option generation, timelines, fuel, separation, turnaround | `sim/` (deterministic simulator) | no |
| Hard constraints (wake, capacity, taxiway, fuel reserve, crew duty, gate, overtime) | `sim/rules/` with rule IDs and sources | no |
| Choosing a move (what to propose, accept, counter, reveal), explaining it | `agents/` (scripted or Claude Haiku 5.5 with tools over its own rules and costs) | **yes** |
| Aggregation, fallback, escalation, turn limit | `protocol/mediator.py` | no |
| Final decision | duty manager in the UI | human |

Disclosure levels: **D0** vetoes only · **D1** rankings · **D2** 0–1 scores per option · **D3** all private data. Acceptance policy (default): an agent accepts a plan up to max($500, 10% of its fallback cost) worse than the fallback.

## Run it
```
pip install -r requirements.txt            # + streamlit, pandas, matplotlib, pyarrow for D
pytest -q                                   # simulator, protocol, guards, log, tracks
python -m protocol.run fixtures/episode_001.json --level D2 --agg nash --decision APPROVE
streamlit run ui/app.py                     # run or replay negotiations; Approve / Override
python -m bench.run --tracks                # benchmark → results/results.parquet (+ tracks C, D)
python -m bench.metrics                     # → results/metrics.md (N, 95% bootstrap CIs)
python -m bench.charts --sensitivity        # → results/charts/*.png, results/sensitivity.md
```
LLM agents: put `ANTHROPIC_API_KEY=...` in `.env` (git-ignored), then use `--agents llm`, or `--llm-subset N` for the benchmark.

## Results
See **[docs/RESULTS.md](docs/RESULTS.md)**. That file holds the demo case, the failure cases, and the adversarial and misreporting tracks. **They currently cover only the 3 synthetic fixtures** and will be regenerated on workstream A's scenarios.

## Data provenance
| Field | Source | Status |
|---|---|---|
| Disrupted flight, schedules, delays, tail numbers | DOT 2015 `flights.csv` (challenge extract) | real |
| Next leg, turnaround slack, gate demand | derived from tail chains | real-derived |
| Runways, gates, max ops/h, min turnaround, wake minima, fuel reserve, burn, spare fuel, crew duty/shift, gate-change notice | organisers' `challenge2_operational_constraints.xlsx` | challenge-specified (its capacity sheet is labelled synthetic by the organisers) |
| Gate assignment and size, connecting passengers, crew start times, weather reduction factor, wake category per tail | generated, seeded | synthetic |
| Fixtures `episode_001-003` | hand-made | synthetic |

Full table and assumptions: `PLAN.md` §3.7 and §5. Deviations from the workbook still to resolve: `PLAN.md` §11 and task B-10.

## Known limits
- Results so far are on 3 fixtures; A's real scenarios are pending.
- Live LLM agents have run on the 3 fixtures only (108 episodes, 0 violations); results vary between runs (see docs/RESULTS.md).
- `sim/params.py` is not yet aligned with the constraints workbook (task B-10).
- Scores at D2 are unit-free on purpose (privacy), which loses magnitude information (see failure case 1).
- One focal flight per scenario; other arrivals keep their slots.

## Layout
`contracts.py` shared schemas · `sim/` simulator, rules, costs · `baselines/` FCFS and best possible · `agents/` scripted, LLM, mock LLM · `protocol/` messages, mediator, log, CLI · `tracks/` adversarial, misreporting · `bench/` runner, metrics, charts · `ui/` Streamlit · `docs/` results, slides · `fixtures/` hand-made scenarios.
