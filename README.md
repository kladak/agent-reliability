# Agent Reliability & Evaluation Platform

**How do we know a tool-using AI agent reliably completes real tasks?**

Portfolio system for Karim Ladak ([github.com/kladak](https://github.com/kladak)) aimed at Applied AI / Forward Deployed / Agent Infrastructure interviews.

This repo contains an agent runtime, schema-validated tools, trace capture, deterministic graders, cost/latency counters, failure taxonomy, and offline regression evals. **Not a chat demo.** UI is optional and secondary to eval/runtime evidence.

## Status

v0 runtime on `feat/runtime-v0`: mock agent + tool router + traces + tasks **T1–T6** + offline eval runner + report compare. Spec: [`SPEC.md`](SPEC.md).

## Quick start (offline, no API keys)

```bash
python -m pip install -e ".[dev]"
make test
make eval-offline
# or:
python -m agent_reliability.eval.runner --offline --report reports/latest-offline.json
```

Compare two reports (pass/fail + failure_class + measured latency/token deltas only):

```bash
python -m agent_reliability.eval.runner --compare reports/baseline.json reports/candidate.json
```

Artifacts:

- `reports/*.json` — pass/fail, latency, tokens, failure class per task
- `traces/*.jsonl` — structured run events (tool calls, retries, resume, policy blocks)

## Package layout

```text
agent_reliability/
  runtime/   # mock agent, state store, policy gate
  tools/     # router + fs_read/fs_write + flaky_echo + http_get
  tasks/     # T1–T6 + deterministic graders
  eval/      # offline runner, JSON reports, compare_reports
  observe/   # TraceEvent JSONL sink + failure taxonomy
fixtures/    # golden inputs for tasks
tests/       # pytest (fully offline)
```

## Task suite

| ID | What it stresses |
|----|------------------|
| `T1_file_repair` | Tool use, JSON validation, idempotent overwrite |
| `T2_api_reconcile` | Mock HTTP fetches, list reconcile, structured report |
| `T3_flaky_tool` | Retries / recovery against injected transient failures |
| `T4_partial_state` | Checkpoint crash mid-run + resume |
| `T5_policy_refusal` | Block unsafe write; `policy_violation`; no side effects |
| `T6_cost_budget` | Finish under token/cost budget (taxonomy for overage) |

## Honesty

- No fabricated production deployments, customers, or model accuracy claims.
- Offline/mock path is first-class so CI does not require paid LLM keys.
- Metrics in reports are only what the runtime measured (latency, token/cost estimates from `MockAgentConfig`, pass/fail). No invented accuracy scores.
- LLM-as-judge is optional and labeled when used (not in this slice).

## Docs

- [SPEC.md](SPEC.md) — problem, architecture, tasks, methodology, success criteria
- [adr/0001-mock-first-evals.md](adr/0001-mock-first-evals.md) — why mock-first CI
