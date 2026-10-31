# The Price of Silos

**Airbus Track, Challenge #2 · Autonomous SG 2026.** Three AI agents, for air traffic control, the airline/pilot and the ground handler, negotiate how to handle a disrupted flight: revised arrival time, gate and flight plan. They do it in at most 3 turns, and each agent sees only its own organisation's data. A deterministic mediator runs the protocol, rule checkers enforce safety, and a duty manager approves the result.

We also ask the question the A-CDM and UDPP debates ask: **how much does each organisation need to share to get most of the benefit?** Our benchmark compares the negotiated plan with three references on 500 scenarios built from real DOT rows: **today's siloed process** (each organisation decides its own part with its own data and phones when a limit breaks), **FCFS/RBS with data shared** (simple dispatch rules, no optimisation), and a **solver that sees everyone's data**.

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
Every scenario carries a `provenance` map (field → `real` / `real_derived` / `organiser` / `synthetic`), and every synthetic flight ID starts with `SYN-`.

| Field | Source | Status |
|---|---|---|
| Disrupted flight: schedule, delays and causes, tail number; inbound-aircraft ready time (`LATE_AIRCRAFT_DELAY`) | DOT 2015 `flights.csv` (organiser extract: 358,774 delayed flights only) | real |
| Neighbouring arrivals at the destination (78% of scenarios have ≥1) | delayed flights in `flights.csv`, at their recorded landing times | real-derived |
| Rest of the arrival stream, up to the arrival rate | seeded filler (`SYN-…`) | synthetic |
| Aircraft's next flight and its scheduled departure (42% of scenarios) | same tail, same day, in `flights.csv` | real-derived |
| Next flight for the other 58% | min turnaround + seeded slack | synthetic |
| Runways, max ops/h, gate and spare-gate counts, min turnaround, wake minima, fuel reserve / contingency / burn / spare, crew duty, ramp shift + 1.5× overtime, 20-min gate-change notice | organisers' `challenge2_operational_constraints.xlsx` | organiser (synthetic values, officially provided) |
| Aircraft size and wake category | heuristic: regional carriers → regional jet; > 2,500 mi → widebody/heavy; else narrowbody/large | synthetic (heuristic) |
| Arrival share of runway ops (½), weather capacity cut, holding-stack limit (30 min), overtime cap (60 min), cruise burn = holding burn | our assumptions, listed in `scenarios/workbook.py` (`OUR_ASSUMPTIONS`) | synthetic (stated) |
| Gate layout and bookings, connecting passengers, crew report times, taxiway closures | seeded draws | synthetic |
| Cost of delay ($67.70/min non-fuel), fuel ($1.20/kg) | A4A 2024 block-minute cost minus fuel; IATA 2026 fuel forecast ($152/bbl) | external, cited in `sim/params.py` |
| Fixtures `episode_001-003` | hand-made | synthetic |

Full table and reasoning: `PLAN.md` §3.7 and §5. `tests/test_scenarios.py` checks the simulator's values against the workbook.

## Known limits
- `flights.csv` holds only delayed flights, so most of each arrival stream is synthetic filler, and a next flight appears only when it was itself delayed.
- Aircraft type is not in the data; size and wake category come from a heuristic.
- The siloed baseline assumes slot updates reach the airline too late, so it absorbs delay by holding in the air unless fuel or the holding stack forces ground delay.
- Scores at D2 are unit-free on purpose (privacy), which loses magnitude information (see failure case 1).
- One focal flight per scenario; other arrivals keep their slots.

## Layout
`contracts.py` shared schemas · `scenarios/` builder (`flights.csv` + workbook → `data/scenarios.jsonl`; `python -m scenarios.sample --n 500`) · `sim/` simulator, rules, costs · `baselines/` siloed, FCFS and best possible · `agents/` scripted, LLM, mock LLM · `protocol/` messages, mediator, log, CLI · `tracks/` adversarial, misreporting · `bench/` runner, metrics, charts · `ui/` Streamlit · `docs/` results, slides · `fixtures/` hand-made scenarios.
