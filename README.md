# Agent Reliability & Evaluation Platform

**How do we know a tool-using runtime reliably runs tasks with traces, policy, and graders?**

Portfolio harness for Karim Ladak ([github.com/kladak](https://github.com/kladak)) aimed at Applied AI / Forward Deployed / Agent Infrastructure interviews.

## Status

**v0 is a deterministic runtime + grader harness**, not a trained LLM agent.

Offline plans are rule-based / fixture-shaped so CI needs no API keys. This slice measures the harness — tool router, traces, failure taxonomy, filesystem sandbox, policy gate, checkpoint resume simulation, budget counters, and deterministic graders — **not** model or agent quality. A live planner is a later adapter behind the same router/trace/grade interfaces.

Spec: [`SPEC.md`](SPEC.md). Branch: `feat/runtime-v0`.

## Quick start (offline, no API keys)

```bash
python -m pip install -e ".[dev]"
make test
make eval-offline
make eval-compare   # diff reports/latest-offline.json vs pinned baseline
# or:
python -m agent_reliability.eval.runner --offline --report reports/latest-offline.json
python -m agent_reliability.eval.runner --compare reports/baseline-offline.json reports/latest-offline.json
```

Artifacts:

- `reports/baseline-offline.json` — **pinned** CI baseline (pass/fail + failure classes; latency zeroed)
- `reports/*.json` — eval outputs (gitignored except the baseline)
- `traces/*.jsonl` — structured run events (tool calls, retries, resume, policy blocks)

## Package layout

```text
agent_reliability/
  runtime/   # mock agent (+ reactive planner loop), state store, policy gate
  tools/     # router + fs_read/fs_write (sandboxed) + flaky_echo + http_get
  tasks/     # T1–T6 + deterministic graders
  eval/      # offline runner, JSON reports, compare_reports
  observe/   # TraceEvent JSONL sink + failure taxonomy
fixtures/    # golden inputs for tasks
tests/       # pytest (fully offline)
```

## Task suite

| ID | What it stresses | What it is / is not |
|----|------------------|---------------------|
| `T1_file_repair` | fs_read → repair broken JSON → idempotent fs_write | Rule-based repair from tool output (not a copy of `expected_*.json`) |
| `T2_api_reconcile` | http_get ×2 → reconcile bodies → write report | Report derived from HTTP tool results |
| `T3_flaky_tool` | Retries against injected transient failures | Fair as a **router** test |
| `T4_partial_state` | Checkpoint + `InjectedCrash` + resume from store | **Simulation** (exception after save), not OS process death |
| `T5_policy_refusal` | Block unsafe write before side effects | **Guardrail** unit path; scripted unsafe step, not model refusal |
| `T6_cost_budget` | Finish under token/cost budget counters | Mock token accrual (`tokens_per_step`), not a real bill |

## Honesty

- No fabricated production deployments, customers, or model accuracy claims.
- The “agent” in v0 is a **scripted / rule-based mock** that drives allowlisted tools. It is a reliability harness with tools, traces, and graders — not evidence that an LLM completes real tasks.
- Offline/mock path is first-class so CI does not require paid LLM keys.
- Metrics in reports are only what the runtime measured (latency, token/cost estimates from `MockAgentConfig`, pass/fail, failure class). No invented accuracy scores.
- CI runs unit tests + offline eval + `--compare` against the pinned baseline (score drop or new/changed `failure_class` / `outcome_failure_class` fails the job).
- LLM-as-judge is optional and labeled when used (not in this slice).

## Docs

- [SPEC.md](SPEC.md) — problem, architecture, tasks, methodology, success criteria
- [adr/0001-mock-first-evals.md](adr/0001-mock-first-evals.md) — why mock-first CI
