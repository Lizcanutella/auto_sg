# Simulator validity check (A-8)

Our knock-on model: next-leg delay = max(0, actual in-block + workbook min turnaround − next leg's scheduled departure). Fed each flight's **recorded** arrival delay and compared with the next leg's **recorded** `LATE_AIRCRAFT_DELAY`. Pairs: every flight in `flights.csv` whose same-tail next leg (from its destination, within 12 h) is also in the file: **146,920 of 358,774 rows (41%)**. Errors are predicted − recorded, in minutes.

| subset                        |       N |   MAE |   median |err| |   bias |   pearson |   spearman | within ±15 min   |
|:------------------------------|--------:|------:|---------------:|-------:|----------:|-----------:|:-----------------|
| all pairs                     | 146,920 |  12.9 |             10 |    6.5 |      0.93 |       0.88 | 72%              |
| predicted >= 20 min           | 137,864 |  11.8 |             10 |    8.8 |      0.96 |       0.91 | 74%              |
| predicted < 20 min            |   9,056 |  28.9 |             17 |  -28.6 |     -0.16 |      -0.1  | 48%              |
| tight slack (<= 15 min spare) | 109,174 |  11.7 |             10 |   10.1 |      0.97 |       0.93 | 73%              |
| loose slack (> 15 min spare)  |  37,746 |  16.1 |             10 |   -3.9 |      0.85 |       0.78 | 69%              |
| Large hub                     |  35,083 |  16.7 |             14 |    9.2 |      0.88 |       0.84 | 59%              |
| Medium hub                    |  57,014 |  11.3 |              8 |    2.2 |      0.93 |       0.88 | 80%              |
| Non-hub                       |  19,350 |  14.1 |             12 |   12.1 |      0.96 |       0.94 | 64%              |
| Small hub                     |  35,473 |  10.9 |              9 |    7.7 |      0.97 |       0.93 | 78%              |

Secondary target (next leg's total `DEPARTURE_DELAY`, all pairs): MAE 17.2, bias -10.7, Pearson 0.82.

## Findings

- **On the fairer subset (predicted ≥ 20 min, N = 137,864)** the model is off by 12 min on average (median 10), with bias +9 min, Pearson 0.96 and Spearman 0.91; 74% of predictions land within ±15 min.
- **The model over-predicts knock-on delay because the workbook's minimum turnaround is longer than what late aircraft actually achieve.** Median turnaround implied by the recorded delays vs workbook minimum (min): Large hub: 32 vs 45; Medium hub: 31 vs 35; Non-hub: 23 vs 35; Small hub: 27 vs 35. Airlines compress turns when running late (regional carriers ~24 min). So the ground agent's `knock_on_delay` cost is an upper bound: it overstates what arriving late costs downstream. We keep the workbook value (organiser rule) and state this.
- **The correlation is high partly by construction.** BTS records `LATE_AIRCRAFT_DELAY` as delay caused by the previous flight of the same aircraft arriving late, which is what the model computes. So this checks our turnaround arithmetic and its parameter, not an independent causal claim.
- **Selection bias: small predictions cannot be scored fairly.** A next leg is only in the file if it was itself delayed (> 20 min late-aircraft, or weather). When we predict < 20 min (N = 9,056; 3% of all pairs predict exactly 0) we only see the next legs that stayed late, so that subset's bias (-29 min) is an artefact. The 59% of flights whose next leg is not in the file are mostly delays that were absorbed, the cases the model would get right; they cannot be scored with this extract.
