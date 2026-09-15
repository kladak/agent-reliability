# ADR 0001: Mock-first agent evals

## Decision
Ship a deterministic mock agent + local tools path as the default CI/eval gate. Optional live LLM providers are additive.

## Why
The signal we want is reproducible traces, graders, and regression gates. Live LLM variance and API keys make CI flaky and hide engineering bugs behind model noise.

## Consequences
A live model can still be enabled for a manual run, but merge gates must pass offline.
