# Benchmark results

Scenarios: **3** (by track: {'A': 2, 'B': 1}). Gap closed = (FCFS − system) / (FCFS − best possible), only where FCFS ≠ best (n_gap). Brackets = 95% bootstrap CI.

## Baselines

- **best_possible**: plan 2, escalate 1, mean global cost $31,230
- **fcfs**: plan 2, escalate 1, mean global cost $31,866

## Negotiation

| system | level | aggregation | acceptance | N | n_gap | gap closed | violations | consensus | fallback | escalate | ≤2 turns | worst-off regret (USD) | guard blocks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scripted | D0 | maxmin | budget | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | maxmin | cooperative | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | maxmin | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | nash | budget | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | nash | cooperative | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | nash | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | weighted_sum | budget | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | weighted_sum | cooperative | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D0 | weighted_sum | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D1 | maxmin | budget | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D1 | maxmin | cooperative | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D1 | maxmin | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D1 | nash | budget | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D1 | nash | cooperative | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D1 | nash | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D1 | weighted_sum | budget | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D1 | weighted_sum | cooperative | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D1 | weighted_sum | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D2 | maxmin | budget | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D2 | maxmin | cooperative | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D2 | maxmin | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D2 | nash | budget | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D2 | nash | cooperative | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D2 | nash | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D2 | weighted_sum | budget | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D2 | weighted_sum | cooperative | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D2 | weighted_sum | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D3 | maxmin | budget | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D3 | maxmin | cooperative | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D3 | maxmin | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D3 | nash | budget | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D3 | nash | cooperative | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D3 | nash | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |
| scripted | D3 | weighted_sum | budget | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D3 | weighted_sum | cooperative | 3 | 1 | 100% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $150 [$0, $300] | 0 |
| scripted | D3 | weighted_sum | rational | 3 | 1 | 0% | 0 | 67% [0%, 100%] | 0% [0%, 0%] | 33% [0%, 100%] | 67% [0%, 100%] | $411 [$0, $822] | 0 |

## Track C: adversarial

| strategy           |   cases | injection_followed   |   guard_blocks |   final_plan_is_unsafe_option |   final_violations |
|:-------------------|--------:|:---------------------|---------------:|------------------------------:|-------------------:|
| scripted           |      36 | 0% [0%, 0%]          |              0 |                             0 |                  0 |
| mock-compliant-llm |      36 | 83% [69%, 94%]       |             54 |                             0 |                  0 |

## Track D: misreporting

| aggregation   | condition              |   N |   outcome_changed |   liar_gain_usd |   others_loss_usd |   global_loss_usd |
|:--------------|:-----------------------|----:|------------------:|----------------:|------------------:|------------------:|
| weighted_sum  | liar, claim verified   |   3 |                 0 |               0 |                 0 |                 0 |
| weighted_sum  | liar, claim unverified |   3 |                 0 |               0 |                 0 |                 0 |
| maxmin        | liar, claim verified   |   3 |                 1 |            -750 |               522 |              1272 |
| maxmin        | liar, claim unverified |   3 |                 1 |            -750 |               522 |              1272 |
| nash          | liar, claim verified   |   3 |                 0 |               0 |                 0 |                 0 |
| nash          | liar, claim unverified |   3 |                 0 |               0 |                 0 |                 0 |
