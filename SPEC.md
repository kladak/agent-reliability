# Agent Reliability & Evaluation Platform — SPEC

**Owner:** Karim Ladak (`kladak`)  
**Repo:** https://github.com/kladak/agent-reliability  
**Status:** Spec for harness v0 (implemented on `feat/runtime-v0`)  
**Core question (north star):** *How do we know a tool-using AI agent reliably completes real tasks?*

> **Honesty (v0):** What ships today is a **deterministic runtime + tool router + trace + grader harness** with a mock/reactive planner — not a trained LLM agent and not proof of general agent quality. T1/T2 use reactive tool loops with derived artifacts; T3–T6 demonstrate router retries, checkpoint-resume **simulation**, policy gating, and budgets. Replay-from-trace regrade, structured-output repair loops, live LLM adapters, and latency p50/p95 are **explicitly out of v0** (tracked as next-slice). CI pins `reports/baseline-offline.json` and fails on pass/fail or failure-class drift.

This is an engineering portfolio system for Applied AI / Forward Deployed / Agent Infrastructure interviews. It is **not** a thin chat wrapper and not a claim of production SLA.


## 1. Problem

Teams ship tool-using agents that demo well and fail quietly: wrong tool args, partial writes, retries that double-charge, missing timeouts, untyped outputs, and “evals” that are vibes. Interviewers ask for **evidence**: traces, failure taxonomy, regression gates, cost/latency, and reproducible comparisons across agent configs.

## 2. Goals (v0)

1. Run multi-step tool-using agents against a **small set of realistic tasks** (not a giant fake benchmark).
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

## 4. Realistic task suite (initial)

Prefer 4–6 tasks with messy constraints:

| ID | Task | Why it stresses agents |
|----|------|------------------------|
| `T1_file_repair` | Fix a broken JSON config and write a valid file | Tool use + validation + idempotent overwrite |
| `T2_api_reconcile` | Call a mock HTTP API, reconcile two lists, write a report | Multi-step + structured output |
| `T3_flaky_tool` | Complete work despite a flaky tool (injected failures) | Retries/timeouts/recovery |
| `T4_partial_state` | Resume after mid-run crash using persisted state | State management + replay |
| `T5_policy_refusal` | Refuse an unsafe/out-of-scope ask without tool side effects | Guardrails + negative tests |
| `T6_cost_budget` | Finish under a token/cost budget or fail with taxonomy | Cost/latency as first-class outcomes |

Tasks use **local fixtures + mock tools** so CI does not need paid LLM keys (mock agent + optional live LLM path).

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

- **`agent_runtime/`** — loop, structured outputs (Pydantic), tool calling, retries, timeouts.
- **`tools/`** — filesystem, mock HTTP, clock, intentional flaky tool; all schema-validated.
- **`tasks/`** — task defs, fixtures, graders, expected artifacts.
- **`eval/`** — runner, datasets, report JSON, failure taxonomy.
- **`observe/`** — trace schema, cost/latency aggregations.
- **`ui/`** (optional) — read-only run inspector (traces, diffs, compare two runs).
- **`adr/`** — architecture decision records.

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
3. **LLM-as-judge** only for open-ended text quality; must record prompt hash/model id; never sole gate for safety tasks.
4. **Regression**: compare to pinned `reports/baseline-offline.json`; CI fails on pass/fail or failure_class / outcome_failure_class drift.
5. **Replay**: re-grade from stored traces without re-calling tools — **not in v0**.

## 8. Reliability mechanisms (v0 status)

- Per-tool timeouts — **present** (thread timeout; cancellation polish later)
- Bounded retries with jitter + idempotency key for write tools — **present** (in-memory idempotency)
- Structured output validation with repair attempt (max 1) — **not in v0**
- Checkpointed state for resume tasks — **present** as InjectedCrash simulation (T4)
- Allowlisted tools only — **present**
- Cost/latency counters on every run — **present** (mock token constants; single wall latency, not p50/p95)
- Replay-from-trace regrade — **not in v0**

## 9. Config comparison

A run config includes: model (or `mock`), tool set, retry policy, temperature, budget. Reports must support side-by-side compare of two configs on the same task set.

## 10. Success criteria for portfolio-ready

- Clone → `make test` and `make eval-offline` work without API keys.
- At least 5 tasks with deterministic graders.
- Traces inspectable; one failure taxonomy applied consistently.
- CI runs unit tests + offline eval regression.
- Independent reviewer challenges methodology; material findings fixed.
- README/SPEC match implementation; no fake production customers or invented accuracy claims.

## 11. Implementation plan (micro-commits)

1. Scaffold package + ADR + SPEC (this doc)
2. Trace schema + state store
3. Tool router + mock tools
4. Agent runtime (mock-first)
5. Tasks T1–T3 + graders
6. Eval runner + reports
7. T4–T6 + resume/budget/refusal
8. CI + offline eval gate
9. Optional minimal UI for traces
10. Independent review → fix → freeze

## 12. Interview talking points (must be true in code)

- “Here’s the trace for a flaky tool run and the retry/idempotency behavior.”
- “Here’s why this grader is deterministic and when we’d use a judge.”
- “Here’s a regression that would fail CI if an agent config regresses.”
- “Here’s cost/latency as outcomes, not afterthoughts.”
