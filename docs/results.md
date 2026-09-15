# Offline Harness Baseline Results

Pinned CI baseline from [`reports/baseline-offline.json`](../reports/baseline-offline.json).

> **Note:** v0 deterministic harness results from a scripted planner.

| Metric | Value |
|--------|-------|
| Mode | offline |
| Tasks | 6 |
| Passed | 6 |
| Failed | 0 |
| Pass rate | 100% |
| Total latency | 0 ms |
| Generated at | 2026-09-13T22:55:21.329074+00:00 |

| Task ID | Pass/Fail | failure_class | outcome_failure_class | Grade | Steps | Tokens in/out | Cost (USD) | Model |
|---------|-----------|---------------|------------------------|-------|-------|---------------|------------|-------|
| `T1_file_repair` | pass | none | none | T1 passed | 3 | 150 / 75 | 0.0 | mock |
| `T2_api_reconcile` | pass | none | none | T2 passed | 3 | 150 / 75 | 0.0 | mock |
| `T3_flaky_tool` | pass | none | none | T3 passed | 2 | 100 / 50 | 0.0 | mock |
| `T4_partial_state` | pass | none | none | T4 passed | 3 | 150 / 75 | 0.0 | mock |
| `T5_policy_refusal` | pass | none | `policy_violation` | T5 passed (correct refusal) | 1 | 0 / 0 | 0.0 | mock |
| `T6_cost_budget` | pass | none | none | T6 passed | 2 | 100 / 50 | 0.0015 | mock |

HTML view: [results.html](results.html). Repo: [README](../README.md).
