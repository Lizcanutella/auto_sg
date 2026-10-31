# Autonomous SG 2026: Airbus Track, Challenge #2

Acacia Hackathon Society x NUS Product Club | AI & Aerospace Track | 31 October 2026

**Datasets:** https://drive.google.com/drive/u/1/folders/13h0JZnSqhYTX3rV8dGDGy5AiwaADQvJR (Challenge #2 data is in `Challenge #2\DATA`)

---

## 1. Problem statement (verbatim from the PDF)

> **"How might AI help air traffic controllers, pilots and ground operations staff make faster and better decisions?"**

### Description
Today, when a runway closes, weather delays occur or ground equipment fail unexpectedly, communications are reliant on human phone calls, manual software updates etc., leading to cascading delays, excessive holding patterns, and excessive fuel consumption. The future of Air Traffic Management relies on AI assistants that can autonomously communicate and negotiate trade-offs across organisational boundaries.

### Want to see
A **Multi-Agent Communication Framework** where ATC AI agents, Pilot AI agents, and ground ops agents are able to negotiate resolutions to real-time disruptions without human intervention until a consensus is reached.

| Agent | Objectives |
|---|---|
| **ATC agent** | Runway wake separation, taxiway blockage, maximise sector throughput |
| **Pilot agent** | Preserve fuel reserves, ensure flight safety, minimise turbulence, protect passengers' connections |
| **Ground agent** | Optimise gate utilisation, avoid ground-crew overtime, minimise turnaround delays |

These 3 agents must exchange structured data, evaluate cross-domain constraints, and converge on an agreed solution. Required elements:
- [ ] Sending **structured messages**
- [ ] **Explicit constraint checking**
- [ ] **Traceable consensus log**
- [ ] **Deterministic non-AI fallback**

### What to avoid
- Combining the 3 roles into a **single prompt call**. The point is to test multi-agent coordination across independent domains.
- LLM agents talking to each other in **endless, unconstrained loops** with no convergence logic or turn limits.
- **Disregarding safety margins.** Agents must not be allowed to accept solutions that ignore operational constraints.

### Provided data
US Department of Transportation data for 2015 flight delays and cancellations.
- File in `Challenge #2\DATA`
- Pick any row with **`WEATHER_DELAY > 15`** or **`LATE_AIRCRAFT_DELAY > 20`**
- Pass the parameters in that row into the 3 AI agents
- Demonstrate how agents negotiate **revised arrival time, gate assignment, or flight plan adjustment in under 3 turns**

#### Dataset notes (our own, verify once downloaded)
This looks like the Kaggle "2015 Flight Delays and Cancellations" set (`flights.csv`, `airlines.csv`, `airports.csv`, about 5.8M rows). Expected columns in `flights.csv`:
`YEAR, MONTH, DAY, DAY_OF_WEEK, AIRLINE, FLIGHT_NUMBER, TAIL_NUMBER, ORIGIN_AIRPORT, DESTINATION_AIRPORT, SCHEDULED_DEPARTURE, DEPARTURE_TIME, DEPARTURE_DELAY, TAXI_OUT, WHEELS_OFF, SCHEDULED_TIME, ELAPSED_TIME, AIR_TIME, DISTANCE, WHEELS_ON, TAXI_IN, SCHEDULED_ARRIVAL, ARRIVAL_TIME, ARRIVAL_DELAY, DIVERTED, CANCELLED, CANCELLATION_REASON, AIR_SYSTEM_DELAY, SECURITY_DELAY, AIRLINE_DELAY, LATE_AIRCRAFT_DELAY, WEATHER_DELAY`

Known gotchas:
- In the Kaggle version, **October 2015 airport codes are 5-digit numeric IDs** instead of IATA codes. Filter out October or map the codes.
- Times are `hhmm` integers (e.g. `1745`), not timestamps.
- The data has **no gates, aircraft type, wake category, fuel on board, crew duty or pax connections**. Anything like that we add is **synthetic and must be labelled as such** (the rubric penalises hidden synthetic data). Same-day flights at the same airport and the `TAIL_NUMBER` chain (next leg of the same aircraft) are real signals we can use for connections, gate pressure and knock-on delay.

---

## 2. Judging rubric

Six criteria, each scored 1 to 5, then weighted. Each project is scored by 3 judges.
**Weighted total / 100 = Σ (score / 5 × weight).** Example: technical soundness 4/5 earns 20 of 25 points.
Scale: 1 = weak, 2 = limited, 3 = credible, 4 = strong, 5 = exceptional evidence.

| Criterion | Weight | Judges ask | Strong | Weak |
|---|---|---|---|---|
| **Technical soundness** | **25%** | Does the prototype work end to end, with the right method for each task? LLMs for reading, retrieval, explanation and interaction. Solvers, rules and statistics for optimisation, scheduling, compliance and detection. Test beyond a scripted demo. | Working inputs and outputs, explicit constraints, a sound LLM / non-LLM split, handles input beyond the demo script. | LLM doing arithmetic, scheduling or legality checks; opaque risk scores; polished UI over a hard-coded scenario. |
| **Problem realism** | 20% | Does this solve a specific aerospace workflow problem? Name the user, current process and cost in time, money or risk. Explain the constraints of *this* challenge, not aviation in general. | Credible named user (e.g. a duty manager), narrow workflow, clear status quo the team understands. | "An AI assistant for aviation", or a solution looking for a problem. |
| **Honest evaluation** | 20% | What was tested, against what baseline, and where does it fail? State metrics, test data and results. Label synthetic data and its limits. Show one case where the system is wrong, uncertain or declines, and explain how the user knows. | A baseline, measured results, a visible failure with a reason and what would fix it. | Only success cases, unsupported accuracy claims, hidden data limits. |
| **Trust and traceability** | 20% | Can a qualified person verify the output before acting? Trace claims to a document/revision/section, a timestamped signal or an applied rule. Handle missing evidence. Keep the qualified person in control. | Checkable sources, visible uncertainty, clear refusal when needed. | Confident unsourced answers, or a claim to replace expert judgement. |
| **Impact** | 10% | What improves over the current process, and by how much? Compare against a stated baseline (e.g. delay minutes). Distinguish measured improvement from estimates. | Credible before/after measure, realistic adoption constraints. | Large benefit claims with no baseline or unstated assumptions. |
| **Time discipline** | 5% | Earlier valid submission is better (recorded submission time), plus a clear, focused presentation **within 3 minutes**. One combined score. | Early submission, focused complete 3-min pitch. | Late submission, rushed or over-time pitch. |

Judges' notes:
- "Where does this fail, and how would your user know?"
- **Reward sound restraint, not presentation polish.**
- Time is only 5%: submitting early does not substitute for quality or evidence.

---

## 3. What solutions to this kind of problem usually look like

### 3.1 The common shape: "LLM proposes, rules dispose"
Almost every credible multi-agent negotiation system for ATM/ops (in research and in hackathons) separates the parts this way, which also matches what the rubric asks for:

```
 DOT row (disruption) ──► Scenario builder (deterministic, + labelled synthetic context)
                                   │
                                   ▼
                      ┌──── Mediator / Orchestrator ────┐   turn limit = 3, state machine
                      │  (deterministic, not an LLM)    │
                      └──┬──────────┬──────────┬────────┘
                         ▼          ▼          ▼
                     ATC agent  Pilot agent  Ground agent    each = separate LLM call
                     + private  + private    + private       + own private state
                     checker    checker      checker         + own hard-constraint validator
                         │          │          │
                         └──── structured JSON messages ────► consensus log (append-only JSONL)
                                   │
                     no consensus after 3 turns / any violation
                                   ▼
                       Deterministic fallback solver ──► Human approval (duty manager)
```

- **LLM jobs:** interpret the disruption, choose which candidate to propose or counter, argue trade-offs in natural language, explain the final plan to the human.
- **Non-LLM jobs:** generate candidate options (ETA slots, gates, reroutes), compute fuel/separation/turnaround numbers, check hard constraints, score options, and pick a fallback.
- An LLM may *propose* something that a rule then *rejects*. That rejection, logged with the rule ID, is the safety story judges want to see.

### 3.2 Negotiation protocols people use
| Protocol | How it works | Fit for "< 3 turns" |
|---|---|---|
| **Mediator + candidate set** (most common, recommended) | Solver enumerates N feasible options; each agent scores them and can veto; mediator picks the best joint option (max-min fairness, Nash bargaining product or weighted sum). | Converges by construction. Turn 1 propose/score, turn 2 counter/concede, turn 3 commit or fall back. |
| **Alternating offers / monotonic concession (Zeuthen)** | Agents take turns making offers; each new offer must be no worse for the others than the previous one. | Guarantees convergence but often needs more than 3 rounds unless the option space is small. |
| **Contract Net (FIPA)** | ATC issues a "call for proposals" (e.g. new slot needed), others bid. | Good for gate/slot allocation; one round each. |
| **Voting / veto** | Each agent approves or vetoes options; first option with unanimous approval wins. | Simple and fast; weak at expressing trade-offs. |

Message types usually follow FIPA-ACL performatives: `PROPOSE`, `COUNTER`, `ACCEPT`, `REJECT`, `INFORM`, plus `constraint_checks: [{rule_id, passed, value, limit}]` and a short `rationale`. Pydantic/JSON-schema validation on every message, with invalid messages counted as a reject.

### 3.3 Typical hard constraints per agent (encoded as rules, not prompts)
| Agent | Hard constraints (veto) | Soft objectives (scored) |
|---|---|---|
| ATC | Wake separation by category (ICAO: e.g. Medium behind Heavy ≈ 5 NM / ~2 min, Light behind Heavy ≈ 6 NM / ~3 min), runway/taxiway closed, runway hourly capacity | Throughput, total holding time |
| Pilot | Fuel on landing ≥ final reserve (~30 min) + alternate + contingency, crew duty limits, no unsafe weather route | Fuel burn, turbulence exposure, passengers' missed connections |
| Ground | Gate free and size-compatible, minimum turnaround time, crew shift end (overtime) | Gate utilisation, turnaround delay, towing moves |

Numbers like reserves and separation should cite their source (ICAO Doc 4444, FAA JO 7110.65, 14 CFR 121.639) in the log. That covers the "trace to an applied rule" part of Trust and traceability.

### 3.4 Deterministic fallback options
- First-come-first-served slot + first available compatible gate (mirrors today's behaviour, so it doubles as the **baseline**).
- Small MILP/CP-SAT (OR-Tools) or a weighted-sum / lexicographic ranking over the same candidate set.
- The fallback must always produce a constraint-satisfying answer or explicitly escalate to the human ("no feasible option").

### 3.5 Tech stacks commonly seen
- Orchestration: plain Python state machine (most transparent), LangGraph, AutoGen, CrewAI, or the Claude Agent SDK / OpenAI Agents SDK. Frameworks are fine, but judges care that the turn limit and validators are explicit.
- Solver: OR-Tools CP-SAT or plain enumeration (the option space per disruption is small).
- UI: Streamlit or a simple React page. Typical layout: disruption card, per-turn message timeline with ✅/❌ constraint chips, final plan, and an **Approve / Override** button for the human.
- Log: JSONL with timestamp, turn, sender, message, checks and decision, replayable.

### 3.6 How strong teams evaluate (Honest evaluation + Impact = 30%)
Run the pipeline over **many** qualifying rows (e.g. 100–500 rows with `WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20`), not one demo row, and report:
- Consensus rate within 3 turns vs fallback rate
- **Hard-constraint violations in final plans (target: 0)**, and how many unsafe LLM proposals the validators caught
- Delay minutes / estimated fuel / missed connections vs the **FCFS baseline** and vs the actual recorded delay
- Latency and LLM cost per disruption
- Ablations: deterministic-only vs LLM-negotiated (does the LLM actually add value?)
- Adversarial cases: impossible scenario (no gate, low fuel), contradictory inputs, agent proposing an unsafe slot. Show the system **declining or falling back**, which counts as the required failure case.
- Clearly state which fields are synthetic (gates, fuel, aircraft type) and how that limits the conclusions.

### 3.7 Common mistakes (that the rubric explicitly punishes)
- One LLM role-playing all three agents in one prompt
- LLMs computing fuel/separation or "deciding" legality
- Unbounded chat between agents
- A single hard-coded scenario behind a nice UI
- No baseline, no failure case, synthetic data not labelled
- Claiming to replace controllers. Frame it as decision support with a human sign-off.

### 3.8 Framing for Problem realism (20%)
Pick one named user and one narrow workflow instead of "AI for ATM". Credible options:
- **Airline Ops Control Centre (OCC) duty manager** handling an inbound flight delayed by weather or a late inbound aircraft: today they coordinate by phone with the tower/TRACON, the crew (via ACARS) and the station's gate/ramp control.
- **Hub station / ramp control supervisor** reassigning gates when inbound flights bunch up.

State the status quo (phone calls, manual gate board updates, ~X minutes per disruption) and the cost (holding fuel, knock-on delay through `TAIL_NUMBER` rotations, missed connections).
