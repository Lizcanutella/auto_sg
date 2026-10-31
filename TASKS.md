# TASKS: The Price of Silos

Companion to `PLAN.md`. Each task has an ID, workstream, priority, dependencies, estimate and a "done when" check.

**Priority:** **P0** = must exist for a valid submission (MVP) · **P1** = what makes us stand out (key chart, honest evaluation) · **P2** = stretch, only after the H8 freeze plan is safe.
**Estimates** are in focused hours for one person. Times like H1/H3 are relative to the kick-off.

---

## 1. How to allocate people

### Fill the workstreams in this order
| Order | Workstream | Why it gets a person first |
|---|---|---|
| 1 | **B: Simulation core** | The critical path. Every agent, baseline and metric uses its numbers. Give it to the most careful coder. |
| 2 | **C: Agents & protocol** | The riskiest part (LLM trial and error). It must start early on scripted agents. |
| 3 | **A: Data & scenarios** | Needed by H3 for real scenarios; until then B and C use the fixture. |
| 4 | **D: Benchmark, UI & pitch** | Can start late with fake results. With fewer people, these tasks are merged into the others. |

### By team size
| Team | Person 1 | Person 2 | Person 3 | Person 4 | Person 5 |
|---|---|---|---|---|---|
| **2** | A + B (+ baselines) | C + D | | | |
| **3** | A + B | C | D + C2 (scripted agents) | | |
| **4** | B | C | A | D | |
| **5** | B | C (mediator, log, scripted) | C (LLM agents, guards, adversarial) | A | D |

With 2 people: **P0 only**, disclosure levels D0 + D2 only, LLM agents on a ≤50-scenario subset.

### When behind schedule, drop in this order
1. P2 tasks (all)
2. D-6 inflated-claims track, D-7 sensitivity analysis
3. C-7 levels D1/D3 (keep D0 + D2)
4. A-6 registry join (fall back to the wake-category heuristic)
5. Number of LLM scenarios (scripted agents still run on everything)

**Never drop:** zero-violation guards (C-5), fallback/escalation (C-2), baselines (B-5, B-6), provenance table (A-7), one shown failure (D-5).

---

## 2. Step 0: everyone (H0 → H1)

| ID | Task | Pri | Est | Done when |
|---|---|---|---|---|
| **S-1** | Agree on decisions: deadline, LLM provider/model/budget, airports in scope, cost weights | P0 | 0.25 | Written at the top of `PLAN.md` §11 |
| **S-2** | `contracts.py`: Pydantic `Scenario`, `Option`, `RuleResult(rule_id, passed, value, limit, source)`, `Message`, `ResultRow`, cost/check function signatures | P0 | 0.5 | Imported by all four workstreams; frozen at H1 (changes need everyone to agree) |
| **S-3** | Hand-written fixture scenario (`fixtures/episode_001.json`) from one real qualifying row | P0 | 0.25 | Loads into `Scenario` without errors |
| **S-4** | Repo skeleton (layout from `PLAN.md` §6), `requirements.txt`, `.env.example`, raw data gitignored | P0 | 0.25 | `pip install -r requirements.txt` works for everyone |
| **S-5** | Ask organisers/Airbus mentors whether a benchmark-centred submission is fine | P0 | 0.1 | Answer recorded in `PLAN.md` |

---

## 3. Workstream A: Data & scenarios

| ID | Task | Pri | Est | Depends on | Done when |
|---|---|---|---|---|---|
| **A-1** | Load `flights.csv` (repo root, 358,774 rows, all qualifying, no October/cancelled/diverted) + workbook; put both `hhmm` times on the destination clock using `SCHEDULED_TIME`, handling arrivals after midnight | P0 | 1 | S-4 | Loader + workbook reader tested; row counts logged |
| **A-2** | Stratified sample by airport size / month / cause (weather rows are only ~12%, so oversample them) | P0 | 0.5 | A-1 | Sample of 500 focal rows with fixed seed |
| **A-3** | Tail chains: next leg in the file (real for 42% of rows) or synthetic next leg | P0 | 1 | A-1 | Every focal row has a next leg tagged real or synthetic |
| **A-4** | Competing arrivals: delayed arrivals in the file (real) + synthetic filler up to the arrival rate (½ × workbook `max_runway_ops_per_hour`, cut for weather) | P0 | 0.75 | A-1 | Each scenario lists its neighbour flights, each tagged real or synthetic |
| **A-5** | Context from the workbook (gates + spare gates, turnaround, fuel, crew duty, ramp shift, gate-change notice) + seeded draws (bookings, connections, report time); aircraft class heuristic | P0 | 1.25 | A-3, A-4, S-2 | `scenarios.jsonl` with ≥100 track-A scenarios **by H3**, every field tagged with its provenance |
| **A-6** | FAA registry join: tail number → aircraft model → wake category; fall back to an airline/distance heuristic | P1 | 1 | A-1 | Match rate reported |
| **A-7** | **Provenance table** (real / real-derived / external / invented, with assumptions), together with D | P0 | 0.5 | A-5 | README provenance table ✅ |
| **A-8** | Simulator check: predicted knock-on delay vs recorded next-leg `LATE_AIRCRAFT_DELAY` (MAE, correlation) | P1 | 1 | A-3, B-3 | `results/sim_validity.md`: MAE 11.8 min, r = 0.96 (predicted ≥ 20 min); over-predicts ~9 min because the workbook turnaround is longer than real ✅ |
| **A-9** | Track B scenarios (infeasible: no gate / fuel below reserve / runway closed) | P0 | 0.5 | A-5 | `data/scenarios_track_b.jsonl`: 20 variants (4 causes) + 19 natural escalations in track A; mediator escalates all ✅ |
| **A-10** | Track E messy-input scenarios (free-text notice/message) + extracted ground-truth constraints | P2 | 1.5 | A-5 | ≥20 text/label pairs |
| **A-11** | Load `challenge2_operational_constraints.xlsx` (PLAN §3.7): per-airport runways, gates, spare gates, max ops/hour, min turnaround; fuel on board = trip + 5% + 30 min reserve + 45 min spare holding; crew duty / shift lengths. Tag these fields as challenge-specified | P0 | 0.75 | A-5 | Scenarios use workbook values for every airport in the sample; provenance table updated |

---

## 4. Workstream B: Simulation core

| ID | Task | Pri | Est | Depends on | Done when |
|---|---|---|---|---|---|
| **B-1** | Option generator: (slot, ground vs airborne delay, gate, route: nominal / reroute / divert) → 20–150 options | P0 | 1 | S-2, S-3 | Deterministic: same input gives same options |
| **B-2** | Rule modules `rules/atc.py`, `pilot.py`, `ground.py`: each rule has an ID, source citation, `check()` → `RuleResult`. Values aligned to the organiser workbook, incl. the gate-change-notice rule | P0 | 1.5 | S-2 | Unit tests: one pass case and one fail case per rule |
| **B-3** | Cost model: private cost per agent + global cost (delay $/min, fuel/CO₂, missed connections, overtime, knock-on delay) | P0 | 1 | B-1 | Costs for every option of the fixture; figures documented with sources |
| **B-4** | Simulator: apply an option → slot sequence, holding, fuel at landing, gate timeline, next-leg delay | P0 | 1 | B-1, B-3 | Used by both baselines and the agents' tools |
| **B-5** | **FCFS/RBS baseline** + **siloed status-quo baseline** (`baselines/siloed.py`) | P0 | 0.5 | B-4 | Produces a plan + cost for any scenario ✅ |
| **B-6** | **Best-possible solver** (enumerate options with all private data) | P0 | 0.5 | B-4 | Never chooses a plan that breaks a rule; always ≤ FCFS cost |
| **B-7** | Review C's guards: every number an agent states must come from B's code | P0 | 0.5 | C-5 | Reviewed: guards hold; number audit is advisory only (see chat notes) ✅ |
| **B-8** | Multi-flight best-possible solver with OR-Tools CP-SAT | P2 | 2 | B-6 | Solves 3+ focal flights jointly |
| **B-9** | Airborne decision-point variant (holding/divert only) | P2 | 1 | B-1 | Option set changes based on the decision point |
| **B-10** | Align `sim/params.py` and rules with the workbook (PLAN §3.7): wake table (+ departure seconds), fuel reserve/contingency/burn, 13 h duty, turnaround, overtime 1.5× cost; new rule **GND-GATE-NOTICE** (gate change ≥ 20 min before arrival); capacity from `max_runway_ops_per_hour`. List every deviation (e.g. overtime hard cap, B757 pairs) for the demo slide | P0 | 1 | B-2, B-3 | Tests updated; deviation list in README |

---

## 5. Workstream C: Agents & protocol

| ID | Task | Pri | Est | Depends on | Done when |
|---|---|---|---|---|---|
| **C-1** | Message schemas + validation (`PROPOSE / COUNTER / ACCEPT / REJECT / ESCALATE`); invalid message counts as `REJECT` | P0 | 0.5 | S-2 | Invalid messages are logged and counted |
| **C-2** | **Mediator state machine**: 3 turns, aggregation rule (weighted sum / max-min / Nash), fallback (RBS + first-fit among non-vetoed options), escalation | P0 | 1.5 | C-1 | `run_episode()` always ends in CONSENSUS, FALLBACK or ESCALATE within 3 turns |
| **C-3** | JSONL consensus log (timestamp, turn, sender, message, rule results, decision) + human Approve/Override entry | P0 | 0.5 | C-2 | An episode can be replayed from the log alone |
| **C-4** | Scripted honest agents (one per role) using B's rules and costs | P0 | 1 | C-2, B-2/B-3 (stub until ready) | **H3: first end-to-end run on the fixture** |
| **C-5** | **LLM agents + hard guards**: tools = the agent's own rules and costs; output schema-validated; cannot ACCEPT its own vetoed option; numbers come only from tools | P0 | 2 | C-4 | 0 violations in final plans across a test batch |
| **C-6** | Disclosure levels D0 (veto) and D2 (scores) | P0 | 0.5 | C-4 | Both run through the benchmark |
| **C-7** | Disclosure levels D1 (ranking) and D3 (all data = best-possible solver) | P1 | 0.5 | C-6 | All 4 levels in the results |
| **C-8** | Track C adversarial: pushing the LLM to accept an unsafe slot, prompt injection in a free-text field, contradictory inputs | P1 | 1 | C-5 | ≥10 cases; how many were blocked is recorded |
| **C-9** | Track D inflated claims: an agent exaggerates costs or falsely claims minimum fuel; verifiable vs unverifiable claims | P1 | 1 | C-4 | Outcome shift measured with and without verification |
| **C-10** | LLM parser for track E messy input → structured constraints, validated | P2 | 1.5 | A-10, C-5 | Extraction accuracy reported |

---

## 6. Workstream D: Benchmark, UI & pitch

| ID | Task | Pri | Est | Depends on | Done when |
|---|---|---|---|---|---|
| **D-1** | Benchmark runner: systems × tracks × disclosure levels → `results.parquet`; parallel; LLM on a fixed subset; cache | P0 | 1.5 | S-2 (fake rows first), C-2 | One command reproduces all results |
| **D-2** | Metrics: gap closed, violations, consensus/fallback/escalation rates, fairness/regret, LLM behaviour (malformed messages, numbers that disagree with tools, giving in too easily, injection success), latency/$; bootstrap confidence intervals | P0 | 1.5 | D-1 | Metrics table with N and CIs |
| **D-3** | **Key chart**: gap closed vs disclosure level, scripted vs LLM | P1 | 0.5 | D-2, C-7 | PNG in slides |
| **D-4** | Streamlit UI: scenario picker, turn timeline, ✅/❌ rule chips, final plan, Approve/Override, results tab | P0 | 2 | C-3 (use a fake log first) | Plays back any logged episode |
| **D-5** | **Choose the demo + failure case** (with C, around H5): a real row where an unsafe proposal is blocked and consensus still forms; one case where the system does worse than FCFS or escalates | P0 | 0.5 | D-1 | Both written up: what happened, why, what would fix it |
| **D-6** | Write up the inflated-claims (track D) results | P1 | 0.5 | C-9 | One slide or README section |
| **D-7** | Sensitivity analysis on cost weights | P1 | 0.5 | D-2 | Headline numbers under ≥3 weightings |
| **D-8** | Slides + README (user/status quo, approach, results, failure, provenance, limits) | P0 | 1.5 | D-2, A-7 | Deck ready by H8 |
| **D-9** | **Early valid submission at H5**, final submission after H8 | P0 | 0.25 | P0 tasks | Submission timestamp recorded |
| **D-10** | Two timed rehearsals of the 3-min pitch | P0 | 0.5 | D-8 | Both rehearsals under 3:00 |

---

## 7. Checkpoints

| When | Gate | What must be true | If it slips |
|---|---|---|---|
| **H1** | Formats frozen | S-1 … S-4 done | Stop and finish them; everything depends on this |
| **H3** | First end to end | C-4 runs the fixture → B-4/B-5/B-6 → one `ResultRow`; A has ≥100 scenarios | Drop all P2 tasks |
| **H5** | MVP + early submission | All P0 tasks done on ≥100 scenarios; D-9 submitted | LLM on a subset only; D0 + D2 only |
| **H8** | Code freeze | Final benchmark runs done; D-5 chosen | Only D edits (slides/README) |
| **H8–H9** | Pitch | D-10 done | |

---

## 8. Ownership board (fill in)

| Workstream | Owner | Backup |
|---|---|---|
| A: Data & scenarios | | |
| B: Simulation core | | |
| C: Agents & protocol | | |
| D: Benchmark, UI & pitch | | |
| Submission + organiser liaison | | |
