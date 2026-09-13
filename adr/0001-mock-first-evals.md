# ADR 0001 — Mock-first agent evals

## Decision
Ship a deterministic mock agent + local tools path as the default CI/eval gate. Optional live LLM providers are additive.

## Why
Portfolio credibility comes from reproducible traces, graders, and regression gates. Live LLM variance and API keys make CI flaky and hide engineering bugs.

## Consequences
Interview demos can still enable a live model, but merge gates must pass offline.
