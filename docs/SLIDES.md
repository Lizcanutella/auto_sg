# 3-minute pitch: slide content and speaker notes (D-8)

Follows `PLAN.md` §9. Numbers marked ⟨…⟩ must be filled from `results/metrics.md` after the run on A's scenarios. **Do not present fixture numbers as results.**

---

### 1. The problem (0:00–0:20)
**Title:** When weather cuts capacity, three organisations fix it by phone.
- Hub duty manager. Thunderstorms cut the arrival rate by 25–40%.
- ATC knows runway capacity and separation. The airline knows fuel and connections. The ground handler knows gates and crew.
- Today: Ration-by-Schedule slots, then phone calls and manual gate boards.

*Notes:* name the user and the cost per delay minute (A4A ~$75 per block minute; **verify before the slide**).

### 2. The insight (0:20–0:50)
**Title:** Each agent keeps its own data. What does that cost?
- 3 agents, each seeing only its own organisation's data.
- Compared against today's process (FCFS) and a solver that sees everything.
- Key question: how much must each organisation share to close the gap?

*Notes:* this is the A-CDM / UDPP debate. Airlines don't want to reveal costs.

### 3. Live demo (0:50–1:40)
Show the UI replaying `results/demo_blocked_unsafe.jsonl`, or a real-scenario equivalent picked from A's data.
- Turn 1: vetoes with rule IDs (✅/❌ chips).
- Turn 2: an attacker pushes ATC to accept gate T5. **The guard blocks it** (`ATC-TWY`: taxiway closed).
- Turn 3: consensus on 19:06 at gate B7. The duty manager clicks **Approve**, and it goes into the hash-chained log.

*Notes:* say "the LLM chooses moves; code computes every number and enforces every rule."

### 4. Results (1:40–2:30)
- Key chart: `results/charts/gap_vs_disclosure.png`. Gap closed by disclosure level, scripted vs LLM.
- ⟨N⟩ scenarios · gap closed at D0 ⟨x%⟩ → D2 ⟨y%⟩ → D3 ⟨z%⟩ · **0 violations** · consensus ⟨c%⟩, fallback ⟨f%⟩, escalation ⟨e%⟩ · median ⟨t⟩ turns.
- Adversarial: unsafe moves attempted ⟨a%⟩, blocked 100%, final-plan violations 0.
- LLM vs scripted: ⟨over-concession, $/episode, latency⟩.

### 5. Where it fails (2:30–2:50)
- More information can give a worse result: at D2 with weighted sum, unit-free scores hide that ATC's loss is only $300 (`docs/RESULTS.md`, failure case 1).
- The system declines when nothing is safe (escalation; Approve is disabled).
- Synthetic inputs: gate layout, passenger counts, weather factor (see the provenance table).

### 6. Impact and next step (2:50–3:00)
- With ⟨level⟩ sharing, agents recover ⟨x%⟩ of the gap, about ⟨$ / min⟩ per disruption (simulated, not measured).
- Deployment needs A-CDM data feeds, airline cost data under UDPP-style privacy, and certification. ATC authority stays with humans.

---
Rehearsal log (D-10): run 1 ⟨mm:ss⟩ · run 2 ⟨mm:ss⟩
