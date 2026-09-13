"""Mock agent runtime that executes explicit multi-step tool plans."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.observe.trace import EventType, TraceEvent, TraceSink
from agent_reliability.tools.router import ToolRouter


class ToolPlanStep(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    # Optional: stop plan early if this step fails
    required: bool = True


class MockAgentConfig(BaseModel):
    model: str = "mock"
    max_steps: int = 20
    # Rough token/cost estimates for mock path (not real LLM usage)
    tokens_per_step: int = 50
    cost_per_1k_tokens: float = 0.0


class RunOutcome(BaseModel):
    run_id: str
    ok: bool
    steps_completed: int
    failure_class: str | None = None
    error: str | None = None
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MockAgentRuntime:
    """Execute a predetermined tool plan through the ToolRouter.

    This is the offline CI path: no paid LLM required. Live model adapters
    can replace plan generation later while keeping the same router/trace.
    """

    def __init__(
        self,
        router: ToolRouter,
        *,
        trace: TraceSink | None = None,
        config: MockAgentConfig | None = None,
    ) -> None:
        self.router = router
        self.trace = trace
        self.config = config or MockAgentConfig()

    def run(self, plan: list[ToolPlanStep], *, run_id: str | None = None) -> RunOutcome:
        rid = run_id or str(uuid.uuid4())
        started = time.perf_counter()
        tokens_in = 0
        tokens_out = 0
        tool_results: list[dict[str, Any]] = []

        if self.trace:
            self.trace.emit(
                TraceEvent(
                    run_id=rid,
                    event_type=EventType.RUN_START,
                    metadata={"model": self.config.model, "plan_len": len(plan)},
                )
            )

        if len(plan) > self.config.max_steps:
            outcome = RunOutcome(
                run_id=rid,
                ok=False,
                steps_completed=0,
                failure_class=FailureClass.INVALID_STRUCTURED_OUTPUT.value,
                error=f"plan length {len(plan)} exceeds max_steps {self.config.max_steps}",
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            self._emit_end(rid, outcome)
            return outcome

        for i, step in enumerate(plan, start=1):
            if self.trace:
                self.trace.emit(
                    TraceEvent(
                        run_id=rid,
                        event_type=EventType.STEP_START,
                        step=i,
                        tool_name=step.tool,
                    )
                )
            # Mock "thinking" tokens
            tokens_in += self.config.tokens_per_step
            tokens_out += self.config.tokens_per_step // 2

            result = self.router.call(
                step.tool,
                step.args,
                step=i,
                idempotency_key=step.idempotency_key,
            )
            tool_results.append(
                {
                    "step": i,
                    "tool": step.tool,
                    "ok": result.ok,
                    "output": result.output,
                    "error": result.error,
                    "failure_class": result.failure_class,
                    "attempt": result.attempt,
                    "cached": result.cached,
                }
            )
            if self.trace:
                self.trace.emit(
                    TraceEvent(
                        run_id=rid,
                        event_type=EventType.STEP_END,
                        step=i,
                        tool_name=step.tool,
                        duration_ms=result.duration_ms,
                        metadata={"ok": result.ok},
                    )
                )

            if not result.ok and step.required:
                cost = ((tokens_in + tokens_out) / 1000.0) * self.config.cost_per_1k_tokens
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=i,
                    failure_class=result.failure_class or FailureClass.UNKNOWN.value,
                    error=result.error,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    tool_results=tool_results,
                )
                self._emit_end(rid, outcome)
                return outcome

        cost = ((tokens_in + tokens_out) / 1000.0) * self.config.cost_per_1k_tokens
        outcome = RunOutcome(
            run_id=rid,
            ok=True,
            steps_completed=len(plan),
            latency_ms=(time.perf_counter() - started) * 1000,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            tool_results=tool_results,
        )
        self._emit_end(rid, outcome)
        return outcome

    def _emit_end(self, run_id: str, outcome: RunOutcome) -> None:
        if self.trace is None:
            return
        self.trace.emit(
            TraceEvent(
                run_id=run_id,
                event_type=EventType.RUN_END,
                error=outcome.error,
                failure_class=outcome.failure_class,
                duration_ms=outcome.latency_ms,
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=outcome.cost_usd,
                metadata={"ok": outcome.ok, "steps_completed": outcome.steps_completed},
            )
        )
