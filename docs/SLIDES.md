# 3-minute pitch: slide content and speaker notes (D-8)

Follows `PLAN.md` §9. Numbers are from the 500-scenario run (`docs/RESULTS.md`). All costs are simulated; say so.

---

### 1. The problem (0:00–0:20)
**Title:** When weather cuts capacity, three organisations fix it by phone.
- Hub duty manager. Weather cuts the arrival rate, or the inbound aircraft is late.
- In **56%** of 481 real-row disruptions, today's siloed process costs more than the best plan.
- ATC knows runway capacity and separation. The airline knows fuel and connections. The ground handler knows gates and crew.
- Today: Ration-by-Schedule slots, then phone calls and manual gate boards.

*Notes:* name the user and the cost per delay minute (A4A 2024: $100.76 per block minute, of which $33.06 fuel; verified 31 Oct).

### 2. The insight (0:20–0:50)
**Title:** Each agent keeps its own data. What does that cost?
- 3 agents, each seeing only its own organisation's data.
- Compared against today's siloed process, FCFS with shared data, and a solver that sees everything.
- Key question: how much must each organisation share to close the gap?

*Notes:* this is the A-CDM / UDPP debate. Airlines don't want to reveal costs.

### 3. Live demo (0:50–1:40)
UI → Replay a log → `results/demo_real_A0266.jsonl`. **JetBlue B6667 MCO → PSE, 30 Dec 2015**, inbound aircraft 35 min late (real row).
- Today's siloed process: departs on time, holds **24 min**, $7,041.
- Turn 1: vetoes with rule IDs (✅/❌ chips): 9 of 68 options survive.
- Turn 2: an attacker pushes ATC to accept an unsafe slot. **The guard blocks it.**
- Turn 3: consensus on ground delay, gate A40: **$5,169, the best possible plan**, $1,872 and 24 min of holding saved. The duty manager clicks **Approve**, and it goes into the hash-chained log.
- Live Claude agents on the same row: same plan in 2 turns.

*Notes:* say "the LLM chooses moves; code computes every number and enforces every rule."

### 4. Results (1:40–2:30)
- Key chart: `results/charts/gap_vs_disclosure.png`. Gap closed vs today's siloed process, by disclosure level.
- 500 real-row scenarios (271 with a gap): **vetoes only 83% → rankings 96–98% → all data 96–100%** (FCFS with shared data: 85%).
- **0 violations in 18,120 episodes**; every episode ends in ≤ 3 turns (consensus in turn 2); escalation correct 100% (19 scenarios have no safe plan).
- Per flight: holding 3.8 → 0 min, extra fuel 231 → 74 kg (simulated).
- Adversarial: worst-case LLM attempted unsafe moves in 40% of 240 cases, all blocked; live Claude followed 0 of 240.
- Live Claude Haiku 5.5: same plan as scripted in 91% of pairs, ~$0.003 per episode; it falsely claimed minimum fuel 89 times, and all were rejected.

### 5. Where it fails (2:30–2:50)
- Vetoes only can be worse than today (6 of 3,252 episodes): the mediator doesn't know the planned gate and picks another, costing $300. Fix: break ties by the agents' first choices.
- Unit-free scores hide dollar magnitudes (a $300 loss can look as big as $1,500 of savings).
- The system declines when nothing is safe (escalation; Approve is disabled).
- Synthetic inputs: gate layout, passenger counts, weather factor (see the provenance table).

### 6. Impact and next step (2:50–3:00)
- Sharing rankings or scores recovers 96–98% of the price of silos: about $500 and 3.8 min of holding per disrupted flight at D2 (simulated, not measured).
- Deployment needs A-CDM data feeds, airline cost data under UDPP-style privacy, and certification. ATC authority stays with humans.

---
Rehearsal log (D-10): run 1 ⟨mm:ss⟩ · run 2 ⟨mm:ss⟩
