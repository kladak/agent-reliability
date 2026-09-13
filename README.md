# Agent Reliability & Evaluation Platform

**How do we know a tool-using AI agent reliably completes real tasks?**

Portfolio system for Karim Ladak ([github.com/kladak](https://github.com/kladak)) aimed at Applied AI / Forward Deployed / Agent Infrastructure interviews.

This repo will contain an agent runtime, schema-validated tools, trace capture, deterministic graders, cost/latency metrics, failure taxonomy, and regression evals. **Not a chat demo.** UI is optional and secondary to eval/runtime evidence.

## Status

Phase 2 just started. Spec is locked in [`SPEC.md`](SPEC.md). Implementation follows in small truthful commits.

## Quick links

- [SPEC.md](SPEC.md) — problem, architecture, tasks, methodology, success criteria

## Honesty

- No fabricated production deployments, customers, or model accuracy claims.
- Offline/mock path is first-class so CI does not require paid LLM keys.
- LLM-as-judge is optional and labeled when used.
