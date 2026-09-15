# Agent Reliability and Evaluation Platform: SPEC

**Owner:** Karim Ladak (`kladak`)  
**Repo:** https://github.com/kladak/agent-reliability  
**Status:** Spec for harness v0 (implemented on `main`)  
**Core question (north star):** *How do we know a tool-using AI agent reliably completes real tasks?*

> **Scope (v0):** a deterministic runtime, tool router, trace sink and grader harness driven by a mock/reactive planner. T1 and T2 use reactive tool loops with derived artifacts; T3 through T6 exercise router retries, checkpoint-resume simulation, policy gating and budgets. Replay-from-trace regrade, structured-output repair loops, live LLM adapters and latency percentiles are scheduled for the next slice. CI pins `reports/baseline-offline.json` and fails on pass/fail or failure-class drift.


## 1. Problem

Teams ship tool-using agents that demo well and fail quietly: wrong tool args, partial writes, retries that double-charge, missing timeouts, untyped outputs, and “evals” that are vibes. What is missing is **evidence**: traces, a failure taxonomy, regression gates, cost/latency accounting, and reproducible comparisons across agent configs.

## 2. Goals (v0)

1. Run multi-step tool-using agents against a small task suite with messy constraints.
2. Capture **structured traces** (steps, tool calls, args/results, errors, timings, token/cost estimates).
3. Grade outcomes with **deterministic graders first**; LLM-as-judge only where justified and labeled.
4. Support **retries, timeouts, failure recovery, idempotency keys** where relevant.
5. Produce **eval reports**: pass/fail, failure class, latency, cost, config comparison, replay from trace.
6. Make runs **inspectable** via CLI + optional minimal UI for traces/comparisons (UI is secondary).

## 3. Non-goals (v0)

- Training models or fine-tuning.
- Multi-tenant SaaS billing / auth productization.
- Claiming human-level agent generality.
- Hundreds of synthetic tasks for leaderboard cosplay.
- Pixel-perfect marketing UI.

## 4. Task suite (initial)

Prefer 4–6 tasks with messy constraints:

| ID | Task | Why it stresses agents |
|----|------|------------------------|
| `T1_file_repair` | Fix a broken JSON config and write a valid file | Tool use + validation + idempotent overwrite |
| `T2_api_reconcile` | Call a mock HTTP API, reconcile two lists, write a report | Multi-step + structured output |
| `T3_flaky_tool` | Complete work despite a flaky tool (injected failures) | Retries/timeouts/recovery |
| `T4_partial_state` | Resume after mid-run crash using persisted state | State management + replay |
| `T5_policy_refusal` | Refuse an unsafe/out-of-scope ask without tool side effects | Guardrails + negative tests |
| `T6_cost_budget` | Finish under a token/cost budget or fail with taxonomy | Cost/latency as first-class outcomes |

Tasks use local fixtures and mock tools, so CI runs offline. A live LLM path can be added behind the same interfaces.

## 5. Architecture

```text
CLI / optional UI
        |
        v
Orchestrator (run config → agent loop)
        |
        +--> Tool Router (allowlist, schemas, timeouts)
        |       idempotency keys, retry policy
        |
        +--> State Store (run state, checkpoints)
        |
        +--> Trace Sink (JSONL events)
        |
        v
Evaluator
        +--> Deterministic graders (schema, file diff, HTTP assertions)
        +--> Optional LLM judge (explicit, version-pinned)
        +--> Metrics (pass, latency p50/p95, cost estimate, failure class)
        |
        v
Report + Regression compare (baseline config vs candidate)
```

### Components

- **`agent_runtime/`**: loop, structured outputs (Pydantic), tool calling, retries, timeouts.
- **`tools/`**: filesystem, mock HTTP, clock, intentional flaky tool; all schema-validated.
- **`tasks/`**: task defs, fixtures, graders, expected artifacts.
- **`eval/`**: runner, datasets, report JSON, failure taxonomy.
- **`observe/`**: trace schema, cost and latency aggregations.
- **`ui/`** (optional): read-only run inspector for traces, diffs and run comparison.
- **`adr/`**: architecture decision records.

## 6. Failure taxonomy (v0)

Every failed run must classify into exactly one primary class:

- `tool_schema_error`
- `tool_execution_error`
- `timeout`
- `retry_exhausted`
- `invalid_structured_output`
- `task_assertion_failed`
- `policy_violation`
- `budget_exceeded`
- `state_corruption`
- `unknown`

## 7. Evaluation methodology

1. **Golden fixtures** checked into repo.
2. **Deterministic graders** preferred (file exists, JSON schema, HTTP mock journal, exact/regex assertions).
3. Open-ended text quality grading is outside v0; current graders are deterministic.
4. **Regression**: compare to pinned `reports/baseline-offline.json`; CI fails on pass/fail or failure_class / outcome_failure_class drift.
5. **Replay**: re-grade from stored traces without re-calling tools. Not in v0.

## 8. Reliability mechanisms (v0 status)

- Per-tool timeout classification: **present** (deadline detection is recorded; workers are not hard-cancelled)
- Bounded retries with jitter plus an idempotency key for write tools: **present** (in-memory idempotency)
- Structured output validation with one repair attempt: **not in v0**
- Checkpointed state for resume tasks: **present** as InjectedCrash simulation (T4)
- Allowlisted tools only: **present**
- Cost and latency counters on every run: **present** (mock token constants; single wall latency, not percentiles)
- Replay-from-trace regrade: **not in v0**

## 9. Config comparison

A run config includes: model (or `mock`), tool set, retry policy, temperature, budget. Reports must support side-by-side compare of two configs on the same task set.

## 10. Acceptance criteria

- Clone -> `make test` and `make eval-offline` work without API keys.
- At least 5 tasks with deterministic graders.
- Traces inspectable; one failure taxonomy applied consistently.
- CI runs unit tests + offline eval regression against the pinned baseline.
- README/SPEC match the implementation: no invented accuracy claims, no unimplemented
  mechanism described as present (see the v0 status table in section 8).
