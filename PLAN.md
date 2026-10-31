# PLAN: The Price of Silos

**Working title:** *The Price of Silos: how much does keeping data inside each organisation cost during a disruption, and can AI agents negotiate it back?*
**Challenge:** Airbus Track #2 (see `CHALLENGE_2.md`) | Autonomous SG 2026 | 31 Oct 2026

---

## 0. One-paragraph pitch

When weather cuts an airport's arrival rate, ATC, the airline and the ground handler each hold part of the picture. ATC knows runway capacity and separation, the airline knows fuel and passenger connections, and the ground handler knows gates and crew shifts. Today they reconcile it by phone. We built the three-agent negotiation framework the brief asks for, where **each agent only sees its own organisation's data**, and we put it inside a **benchmark** built from real 2015 DOT disruptions. The benchmark compares the negotiated outcome against two references: **today's rule-of-thumb process** (first-come-first-served) and a **solver that sees everyone's data**, the best possible outcome. The headline number is **how much of the gap between those two the agents close, how much data they had to share to do it, and whether any unsafe plan got through** (the target is zero).

---

## 1. Why this angle (and why it's still on-brief)

| Brief requirement | Where it is in our build |
|---|---|
| 3 independent agents (ATC, Pilot, Ground) | Separate processes/calls, each with its **own private data and its own constraint checker** |
| Structured messages | Pydantic-validated JSON messages (`PROPOSE / COUNTER / ACCEPT / REJECT / ESCALATE`) |
| Explicit constraint checking | Deterministic rule modules with rule IDs that cite their sources |
| Traceable consensus log | Append-only JSONL with every message, check, score and decision, replayable in the UI |
| Deterministic non-AI fallback | Ration-by-Schedule + first-fit gate, restricted to options nobody vetoed, or escalate to the human |
| Under 3 turns (one turn = each of the 3 agents sends one structured message) | Hard state machine: Turn 1 evaluate, Turn 2 counter, Turn 3 commit, otherwise fallback, with the reason logged |
| Use a row of `flights.csv` (all rows qualify) | Every benchmark scenario is built around such a row (the **focal flight**) |
| Use the limits in `challenge2_operational_constraints.xlsx`; state any change | Builder reads the workbook; every value we change or add is listed on a "Changed / added limits" slide |

What we add on top, which is what most teams won't have:
**baselines, a best-possible reference, hundreds of scenarios, adversarial cases, and a measured answer to "do the LLMs actually help?"**

---

## 2. Problem realism: user, status quo, cost

- **Named user:** the **airline hub duty manager** (Operations Control Centre / station ops at a US hub such as ATL, ORD or DFW), who signs off the plan. Secondary users: the tower/TRACON traffic management coordinator and the ramp/gate controller.
- **Status quo (US, 2015 context):** when capacity drops, the FAA Command Center runs a Ground Delay Program and assigns arrival slots by **Ration-by-Schedule (RBS)**, which is first-come-first-served on scheduled time. Airlines can swap slots among their own flights. Gate and crew rearrangements then happen through phone calls, radio and manual gate-board updates. The FAA Command Center also holds planning teleconferences roughly every two hours.
- **Real-world equivalents we can cite:** Europe's **A-CDM** (Airport Collaborative Decision Making), where the airport, airlines, ATC and ground handlers share milestone times through a portal, and EUROCONTROL's **UDPP** (User-Driven Prioritisation Process), where airlines reprioritise their own flights *without revealing their costs*. Both show that the industry already argues about **how much each party should share**. That is exactly our experiment.
- **Cost of a delay minute (verified 31 Oct):** **$100.76 per block minute** for US passenger airlines in 2024, of which $33.06 is fuel and $35.23 labour (Airlines for America, "U.S. Passenger Carrier Delay Costs", airlines.org). Europe: about **€104 per minute** of tactical delay (2018 value; EUROCONTROL Standard Inputs, from University of Westminster studies). Our model uses the non-fuel $67.70/min and costs fuel separately at $1.20/kg (IATA's June 2026 forecast: $152/bbl). Add holding fuel/CO₂, missed connections, and knock-on delay to the aircraft's later flights.

---

## 3. System design

### 3.1 Scenario = one disruption episode
Built from a **focal flight** (a row of `flights.csv`) plus context. `flights.csv` holds only delayed flights, not the full schedule, so context is part real, part synthetic:
- **Competing arrivals:** delayed flights in the file arriving at the same destination in the window are **real**. The rest of the arrival stream, up to the airport's arrival rate, is **synthetic filler** (labelled). On big storm days (e.g. 58 delayed ATL arrivals in one hour) most of the stream is real.
- **Same-aircraft chain:** when the focal tail's next same-day leg is in the file (42% of rows), its schedule and recorded `LATE_AIRCRAFT_DELAY` are **real**. That is the knock-on delay we try to reduce. Otherwise the next leg is **synthetic** (scheduled after the airport's minimum turnaround plus seeded slack).
- **Gates:** per-airport gate count and `spare_gates_at_any_time` from the workbook (**synthetic, organiser-provided**). Each scenario gets the planned gate plus the spare gates, with seeded bookings.
- **Capacity:** arrival rate = half of the workbook's `max_runway_ops_per_hour` (**our assumption**: the other half is departures). For weather rows it is cut by a seeded factor scaled by `WEATHER_DELAY` (**synthetic, labelled**). Late-aircraft rows keep normal capacity: there the disruption is the late inbound aircraft itself.
- **Decision point:** before departure from the origin, so ground delay at the origin is still an option. This mirrors how Ground Delay Programs work: taking delay on the ground is much cheaper than airborne holding. A second variant at T-45 min, airborne, leaves only holding, rerouting or diverting.

### 3.2 Options (each one fully computed by the simulator)
`option = (arrival slot, delay absorption: ground | airborne holding, gate, route: nominal | weather reroute | divert to alternate)`

The option generator is **deterministic** and lists a small set (~20–150 options), which keeps both the best-possible solver and the negotiation tractable.

### 3.3 Private data and checks per agent

Limits come from the organiser workbook unless marked otherwise.

| Agent | Private data (others can't see it) | Hard constraints (veto, rule ID + source) | Private cost |
|---|---|---|---|
| **ATC** | Slot sequence, arrival rate, wake category of neighbours, taxiway closures | Slot capacity per hour; wake separation (workbook `wake_separation`, from FAA JO 7110.65); gate unreachable when its taxiway is closed; holding-stack limit (ours) | Sector holding minutes, throughput loss |
| **Pilot / Airline** | Fuel on board, burn rate, connecting passengers, crew report time | Landing fuel ≥ 30 min holding reserve (workbook; alternate fuel optional, off by default); crew duty ≤ 13 h from report (workbook, simplified Part 117); no route through the weather cell | Fuel kg/CO₂, passenger-delay minutes, missed connections |
| **Ground** | Gate bookings, planned gate, ramp crew shift | Gate free and size-compatible; **gate change notified ≥ 20 min before arrival** (workbook); overtime cap (ours) | Overtime minutes (1.5× after the 8 h shift, workbook), turnaround delay, gate changes |

Fuel on board is derived from the workbook: trip fuel + 5% contingency + 45 min spare holding + 30 min final reserve. We read "45 min spare" as fuel on top of the final reserve, and we state that reading in the demo.

**Rule:** the LLM never decides legality. Every proposal passes through the sender's own checker before it is sent and through the mediator's schema validator on receipt. An agent **cannot ACCEPT an option its own checker vetoed**; the code enforces this regardless of what the LLM says.

### 3.4 Protocol (mediator = deterministic state machine)
```
Turn 1  Mediator ─► all: disruption + option IDs + public data
        each agent: run own checker → vetoes; produce preference (depends on disclosure level D0-D3); short rationale
Turn 2  Mediator: drop vetoed options → rank remaining by aggregation rule → propose top-k
        each agent: ACCEPT one | COUNTER (concede, reveal more, or request a variant) | REJECT
Turn 3  Mediator: final joint proposal → unanimous ACCEPT ⇒ CONSENSUS
        otherwise ⇒ FALLBACK: RBS slot + first-fit gate among non-vetoed options (log why consensus failed)
        (organiser definition: one turn = each of the 3 agents sends one structured message)
        no non-vetoed option ⇒ ESCALATE to duty manager ("no safe plan found", with reasons)
Human   Duty manager sees plan + rule trace + alternatives → Approve / Override (logged)
```
Aggregation rule (the mediator's choice): weighted sum, max-min fairness or Nash bargaining. **This is an experiment setting, not a fixed choice.**

### 3.5 Disclosure levels: the core experiment
| Level | What each agent sends the mediator |
|---|---|
| **D0** Veto only | Acceptable / not acceptable per option |
| **D1** Ranking | Ranked preferences, no numbers |
| **D2** Scores | Numeric private cost per option |
| **D3** Full data | Raw private data, i.e. the best-possible solver |

**Key chart:** gap closed (y-axis) against disclosure level (x-axis), plotted separately for scripted agents and LLM agents. This answers *how much does each organisation need to share to get most of the benefit?*, a question the A-CDM and UDPP debates care about directly.

### 3.6 Where the LLM sits (and where it doesn't)
| Job | LLM? | Why |
|---|---|---|
| Parse messy inputs (free-text weather/airport notice, crew notes) into structured constraints | ✅ | Reading is what language models are for; validated by schema + cross-check |
| Choose a strategy: what to concede, what to reveal, what to counter with | ✅ (tested against scripted) | This is the open question, so we measure it |
| Write the rationale and the explanation for the duty manager | ✅ | Explanation |
| Fuel / separation / turnaround arithmetic | ❌ | Tools / simulator |
| Legality / constraint satisfaction | ❌ | Rule modules |
| Picking the final plan, fallback | ❌ | Mediator + solver |

### 3.7 Organiser constraints workbook (`challenge2_operational_constraints.xlsx`)
The organisers' workbook says: *"Use the limits in this workbook. Any limit you change must be stated in your demo."* It replaces most of the values we were going to invent. Its `airport_capacity` sheet is itself labelled **synthetic** by the organisers ("scaled from each airport's traffic in flights.csv"), so in the provenance table these values are **challenge-specified**, not real.

| Sheet | Values | Used by | Replaces |
|---|---|---|---|
| `airport_capacity` (324 airports) | size class, active runways, gates, max runway ops/hour, min turnaround, spare gates at any time | scenario builder (A), ATC capacity rule, ground turnaround/gate rules (B) | our gate counts, base AAR estimate, turnaround constant |
| `wake_separation` | NM on approach and seconds between same-runway departures per leader/follower pair; "any other pair" 3 NM / 60 s | ATC wake rule (B) | B's own FAA table (the workbook has **no B757 rows** and lists only these pairs) |
| `fuel_and_crew` | final reserve 30 min holding fuel; contingency 5% of trip fuel; holding burn 2,400 / 6,500 kg/h; spare fuel on arrival 45 min holding; crew duty 13 h from report; ground shift 8 h, overtime 1.5×; gate change notice ≥ 20 min before arrival | pilot fuel/duty rules, ground cost and new gate-notice rule (B); fuel on board in scenarios (A) | random fuel on board, invented crew limits |
| `rules_of_play` | one turn = each agent sends one structured message; consensus within 3 turns; deterministic fallback after 3 turns, log why; output = revised arrival time, gate or flight plan + consensus log per turn | mediator (C) | (already matches our protocol) |

**Still ours (synthetic, labelled):** which gate each tail uses and gate sizes; wake category per aircraft (FAA registry join, else heuristic); connecting-passenger counts; crew report / shift start times; weather capacity reduction factor; the share of `max_runway_ops_per_hour` available to arrivals.

**Where we deviate from the workbook, we must say so in the demo.** Done: wake table = workbook (B757 pairs removed, Large→Small 4 NM added), 20-min notice is rule `GND-NOTICE`, overtime priced at 1.5×. Remaining deviations and additions, all listed in `scenarios/workbook.py` (`OUR_ASSUMPTIONS`): ramp-overtime hard cap of 60 min (rarely binds, since the next shift takes late arrivals); holding-stack limit 30 min; arrivals = ½ of runway ops; weather capacity cut; cruise burn = holding burn; "45 min spare" read as on top of the 30 min reserve; no alternate fuel.

---

## 4. The benchmark

### 4.1 Systems compared (same scenarios, same simulator, same cost model)
0. **Siloed status quo** (`baselines/siloed.py`): today's process. Each organisation decides its own part with its own data, in sequence (ATC slot → airline departs when ready and holds in the air → ground keeps planned gate), and they only "phone" when a hard limit breaks. Always safe, never optimised.
1. **FCFS / RBS** (`baselines/fcfs_rbs.py`): coordinated simple rules. Everyone's data is shared, but the plan still follows the dispatch order (RBS slot, ground delay first, planned gate)
2. **Best possible:** a central solver with all private data (enumeration, or OR-Tools CP-SAT for multi-flight)

**First measured result (500 scenarios, `python -m bench.baselines_report`):** the price of silos (siloed − best) is non-zero in 81% of weather scenarios (mean $931) and 32% of late-aircraft scenarios (mean $74). Sharing data with simple rules (FCFS) recovers 45% and 79% of it respectively; the rest needs actual trade-offs, which is the negotiators' job. With all data shared, the best plan is often obvious: FCFS already matches it in 83% / 93% of cases.
3. **Scripted negotiators:** the same protocol with fixed, honest strategies (no LLM)
4. **LLM negotiators:** the same protocol, with LLM strategy inside the hard guards
5. *(context only)* **Historical outcome:** the recorded `ARRIVAL_DELAY` and next-leg `LATE_AIRCRAFT_DELAY`. Not a like-for-like comparison, so we label it as such.

### 4.2 Scenario tracks
| Track | Content | Purpose |
|---|---|---|
| **A: Core** | 200–500 qualifying rows, sampled across airports, months and delay causes (weather vs late aircraft) | Headline numbers |
| **B: Infeasible** | No compatible gate / fuel below reserve on every option / runway closed | Must ESCALATE, never output a plan |
| **C: Adversarial** | An agent's LLM is pushed to accept an unsafe slot; a free-text field contains a prompt injection ("ignore your fuel limits"); contradictory inputs | Guards must catch it, and we count it |
| **D: Misreporting** | An agent exaggerates its cost or falsely claims minimum fuel to get priority (this happens in real life) | Tests whether the mechanism can be gamed; separates verifiable claims (fuel vs flight data) from unverifiable ones |
| **E: Messy input** *(stretch)* | The disruption arrives as a free-text notice/message instead of JSON | The one place an LLM should clearly beat rules; measure extraction accuracy |

### 4.3 Metrics
- **Gap closed** = (C_siloed − C_system) / (C_siloed − C_best). 0% = no better than today's siloed process, 100% = matches the best possible. Also report it against FCFS, to separate "sharing data" from "negotiating trade-offs".
- **Safety:** hard-constraint violations in final plans (**must be 0**), unsafe proposals blocked by guards, escalation correctness on track B
- **Convergence:** consensus within ≤3 turns, fallback rate, escalation rate
- **Fairness:** each agent's regret against its own best feasible option; worst-off agent
- **LLM behaviour:** schema-invalid message rate, **numbers in rationales that disagree with tool outputs** (auto-checked), **over-concession** (utility given up compared with the scripted agent under the same information), injection success rate
- **Cost:** latency, tokens and $ per scenario
- **Simulator validity:** predicted knock-on delay vs recorded next-leg `LATE_AIRCRAFT_DELAY` (MAE / correlation). This tests our own model against real data.
- **Sensitivity:** recompute the headline numbers under different cost weights (fuel vs delay vs connections)

### 4.4 Honest-evaluation deliverables (for the slide and README)
- A table of every metric × system, with N and confidence intervals (bootstrap)
- A **data provenance table**: each field marked real (DOT), real-derived (tail chains), external (FAA registry), or synthetic, with the assumptions behind it
- At least **one shown failure**: a case where the LLM negotiators do worse than FCFS, or the fallback picks a poor plan, with why and what would fix it
- One shown **escalation** (track B) and one **blocked unsafe proposal** (track C) in the UI

---

## 5. Data plan

| Field | Source | Real? |
|---|---|---|
| Focal flight: schedule, delays, causes, tail number | `flights.csv` (DOT 2015, delayed flights only) | ✅ Real |
| Next leg + its recorded knock-on delay (42% of rows) | Same tail, same day, in `flights.csv` | ✅ Real-derived |
| Next leg for the other 58% | Min turnaround + seeded slack | ❌ Synthetic |
| Competing arrivals | Delayed arrivals in the file (real) + filler up to the arrival rate | ⚠️ Mixed, labelled per flight |
| Runway capacity, gates, spare gates, min turnaround | Workbook `airport_capacity` | ⚠️ Organiser synthetic |
| Arrival rate | ½ × `max_runway_ops_per_hour` (our assumption) × weather cut (seeded, scaled by `WEATHER_DELAY`) | ❌ Synthetic |
| Wake separation | Workbook `wake_separation` (from FAA JO 7110.65) | ⚠️ Organiser, simplified real rule |
| Aircraft class / wake category | Heuristic: regional carriers (OO, EV, MQ) → regional; distance > 2,500 mi → widebody/heavy; else narrowbody/large. FAA registry join optional (A-6) | ❌ Heuristic, labelled |
| Fuel (burn, reserve, contingency, spare) | Workbook `fuel_and_crew`; trip fuel from `AIR_TIME` × cruise burn (our assumption) | ⚠️ Organiser + our assumption |
| Crew duty, ramp shift, gate-change notice | Workbook `fuel_and_crew`; report time and shift boundaries seeded | ⚠️ Organiser + synthetic |
| Connecting passengers | Seeded | ❌ Synthetic |

Gotchas: times are `hhmm` integers; departure is origin-local and arrival destination-local (convert with `SCHEDULED_TIME`, watch for arrivals after midnight); fix the random seed for every synthetic draw. (No October rows and no cancelled/diverted rows in this extract.)

---

## 6. Architecture and repo layout

Plain Python, no agent framework required. A small state machine is easier to explain and audit.

```
flights.csv, challenge2_operational_constraints.xlsx   organiser data (repo root)
scenarios/       builder: flights.csv + workbook -> Scenario; writes data/scenarios.jsonl
sim/
  scenario.py    build episode from focal row (+ synthetic context, seeded)
  options.py     deterministic option generator
  costs.py       per-agent private cost + global cost
  rules/         atc.py pilot.py ground.py  (each rule: id, source, check() -> pass/fail + values)
agents/
  base.py        Agent interface: evaluate(options, level) -> Message
  scripted.py    honest scripted strategy
  llm.py         LLM strategy; tools = own rules + own costs; output schema-validated
protocol/
  messages.py    pydantic schemas
  mediator.py    3-turn state machine, aggregation rules, fallback, escalation
  log.py         JSONL consensus log
baselines/       fcfs_rbs.py, best_possible.py
bench/
  run.py         systems × tracks × disclosure levels → results.parquet
  metrics.py, report.ipynb
ui/              Streamlit: scenario picker, turn-by-turn timeline, ✅/❌ rule chips, plan, Approve/Override, results tab
```

**LLM choice:** a fast, cheap model for agents in bulk runs (e.g. Claude Haiku 5.5), and optionally a stronger one on a subset to see whether model strength matters. Up to 9 calls per scenario, so 300 scenarios × 2 disclosure levels ≈ 5k calls. Run in parallel, cache prompts, and run **scripted agents on everything and LLM agents on a fixed subset** if budget or time is tight.

---

## 7. Scope ladder

**MVP (must exist to submit)**
- [ ] Scenario builder for one airport-day window + focal row
- [ ] Option generator, cost model, 3 rule modules with IDs
- [ ] Mediator (3 turns, fallback, escalation) + JSONL log
- [ ] Scripted agents + LLM agents (D0 and D2 at minimum)
- [ ] FCFS and best-possible baselines
- [ ] Bench run on ≥100 track-A scenarios + a handful of B/C scenarios
- [ ] Streamlit view of one negotiation + results table
- [ ] Provenance table + one failure case

**Should**
- [ ] All 4 disclosure levels → the key chart
- [ ] FAA registry wake categories
- [ ] Simulator validity check against next-leg `LATE_AIRCRAFT_DELAY`
- [ ] Sensitivity to cost weights, fairness metrics
- [ ] Track D misreporting

**Stretch**
- [ ] Track E messy text input
- [ ] Multi-flight negotiation (several focal flights at once, CP-SAT best-possible solver)
- [ ] Airborne decision-point variant

---

## 8. Day timeline (relative; adjust to the submission deadline)

Time discipline is only 5%, but it is cheap points. Aim to submit a valid MVP early and then improve it.

| Block | Data & sim | Agents & protocol | Bench & UI & pitch |
|---|---|---|---|
| H0–H1 | Load DOT, qualifying-row filter, tail chains | Message schemas, mediator skeleton | Repo, metric definitions, provenance table draft |
| H1–H3 | Scenario builder, option generator, costs, rules | Scripted agents end to end | FCFS + best-possible baselines |
| H3–H5 | Synthetic context, seeds, registry join | LLM agents + guards, log | Bench runner, first numbers |
| H5–H6 | **MVP freeze → submit early version** | | |
| H6–H8 | Validity check, tracks B/C | Disclosure levels D1/D3, adversarial prompts | Streamlit UI, key chart |
| H8–H9 | Bug fixes | Failure-case hunt | Final runs, slides, **rehearse 3-min pitch** |

---

## 9. Three-minute pitch outline
1. **(0:20) User and pain:** hub duty manager, weather cuts arrival rate, phone calls between three organisations, $/min.
2. **(0:30) Insight:** the reason for three agents is that each organisation keeps its own data. So what does that cost, and can negotiation recover it?
3. **(0:50) Live demo:** one real DOT row → 3 turns → a blocked unsafe proposal → consensus → duty manager approves. Show the log.
4. **(0:50) Results:** gap closed per system; chart of results against disclosure level; 0 violations; consensus/fallback/escalation rates.
5. **(0:20) Where it fails:** a shown failure + what's synthetic.
6. **(0:10) Impact and next step:** what a real deployment would need (A-CDM data feeds, airline cost data under UDPP-style privacy).

---

## 10. Hypotheses (state them before running, report honestly after)
- H1: Scripted D2 negotiation closes most of the gap (>60%); D0 closes much less.
- H2: LLM agents don't beat scripted agents on clean numeric scenarios at the same disclosure level, and may over-concede.
- H3: LLM agents add value on messy input (track E) and in explanations.
- H4: With guards, final-plan violations are 0 even though LLMs propose unsafe options in track C.
- H5: Without verification, misreporting (track D) shifts outcomes towards the liar. Verifiable claims fix this.

**Any of these turning out false is a result, not a failure.** The rubric rewards restraint and honesty.

---

## 11. Open decisions for the team
- [ ] Team size and roles; exact submission deadline
- [ ] LLM provider, model and budget
- [ ] Airports in scope (one big hub such as ATL, or top-5)
- [ ] Global cost weights (pick defaults with citations; sensitivity covers the rest)
- [ ] Ask the organisers/Airbus mentors: is a benchmark-centred submission fine, as long as the framework is fully built? (Expected: yes.)
- [x] **Align with the constraints workbook (§3.7):** done; `tests/test_scenarios.py` checks the sim's values against the workbook. Overtime cap kept as a stated assumption; B757 pairs removed.
- [x] 20-min gate-change notice (`GND-NOTICE`) and per-airport capacity added; arrival share = ½ (stated assumption).
- [x] Provenance value for organiser data: implemented as `Provenance.ORGANISER = "organiser"` (proposed as `CHALLENGE`; same meaning).

## 12. Glossary
**AAR** airport arrival rate (arrivals/hour) · **RBS** Ration-by-Schedule, the FAA's default slot allocation · **GDP** Ground Delay Program · **A-CDM** Airport Collaborative Decision Making · **UDPP** User-Driven Prioritisation Process · **OCC** airline Operations Control Centre · **TRACON** terminal radar approach control · **Wake category** leader/follower aircraft classes that set minimum spacing
