# Agent Reliability & Evaluation Platform

**How do we know a tool-using AI agent reliably completes real tasks?**

Portfolio system for Karim Ladak ([github.com/kladak](https://github.com/kladak)) aimed at Applied AI / Forward Deployed / Agent Infrastructure interviews.

This repo contains an agent runtime, schema-validated tools, trace capture, deterministic graders, cost/latency counters, failure taxonomy, and offline regression evals. **Not a chat demo.** UI is optional and secondary to eval/runtime evidence.

## Status

v0 runtime slice on `feat/runtime-v0`: mock agent + tool router + traces + tasks **T1** / **T3** + offline eval runner. Spec remains in [`SPEC.md`](SPEC.md).

## Quick start (offline, no API keys)

```bash
python -m pip install -e ".[dev]"
make test
make eval-offline
# or:
python -m agent_reliability.eval.runner --offline --report reports/latest-offline.json
```

Artifacts:

- `reports/*.json` — pass/fail, latency, tokens, failure class per task
- `traces/*.jsonl` — structured run events (tool calls, retries, timings)

## Package layout

```text
agent_reliability/
  runtime/   # mock agent loop over tool plans
  tools/     # router + fs_read/fs_write + flaky_echo
  tasks/     # T1_file_repair, T3_flaky_tool (+ graders)
  eval/      # offline runner + JSON reports
  observe/   # TraceEvent JSONL sink + failure taxonomy
fixtures/    # golden inputs for tasks
tests/       # pytest (fully offline)
```

## Tasks in this slice

| ID | What it stresses |
|----|------------------|
| `T1_file_repair` | Tool use, JSON validation, idempotent overwrite |
| `T3_flaky_tool` | Retries / recovery against injected transient failures |

Still to come (see SPEC): `T2_api_reconcile`, `T4_partial_state`, `T5_policy_refusal`, `T6_cost_budget`.

## Honesty

- No fabricated production deployments, customers, or model accuracy claims.
- Offline/mock path is first-class so CI does not require paid LLM keys.
- Metrics in reports are only what the runtime measured (latency, token estimates from `MockAgentConfig`, pass/fail). No invented accuracy scores.
- LLM-as-judge is optional and labeled when used (not in v0 slice).

## Docs

- [SPEC.md](SPEC.md) — problem, architecture, tasks, methodology, success criteria
- [adr/0001-mock-first-evals.md](adr/0001-mock-first-evals.md) — why mock-first CI
