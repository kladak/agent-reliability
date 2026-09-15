# ADR 0001: Mock-first agent evals

## Decision
Ship a deterministic mock agent + local tools path as the default CI/eval gate. Live LLM providers are outside v0.

## Why
The signal we want is reproducible traces, graders, and regression gates. Live LLM variance and API keys make CI flaky and hide engineering bugs behind model noise.

## Consequences
The v0 runner accepts offline invocation only.
