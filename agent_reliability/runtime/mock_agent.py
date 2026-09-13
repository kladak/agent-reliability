"""Mock agent runtime that executes explicit multi-step tool plans."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from pydantic import BaseModel, Field

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.observe.trace import EventType, TraceEvent, TraceSink
from agent_reliability.runtime.policy import PolicyGate
from agent_reliability.runtime.state_store import Checkpoint, StateCorruptionError, StateStore
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
    # Budgets: None means unlimited. Checked after each step's token accrual.
    max_tokens: int | None = None
    max_cost_usd: float | None = None


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


class InjectedCrash(Exception):
    """Stand-in for a mid-run process death after a checkpoint was saved.

    T4 catches this and resumes from the state store — not a cooperative
    RunOutcome return on the happy path.
    """


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
        state_store: StateStore | None = None,
        policy: PolicyGate | None = None,
    ) -> None:
        self.router = router
        self.trace = trace
        self.config = config or MockAgentConfig()
        self.state_store = state_store
        self.policy = policy or PolicyGate()

    def run(
        self,
        plan: list[ToolPlanStep],
        *,
        run_id: str | None = None,
        resume: bool = False,
        crash_after_step: int | None = None,
    ) -> RunOutcome:
        rid = run_id or str(uuid.uuid4())
        started = time.perf_counter()
        tokens_in = 0
        tokens_out = 0
        tool_results: list[dict[str, Any]] = []
        start_index = 0  # 0-based index into plan
        resumed = False

        if resume and self.state_store is not None:
            try:
                ckpt = self.state_store.load(rid)
            except StateCorruptionError as exc:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=0,
                    failure_class=FailureClass.STATE_CORRUPTION.value,
                    error=str(exc),
                    latency_ms=(time.perf_counter() - started) * 1000,
                    metadata={"resume_attempted": True},
                )
                self._emit_end(rid, outcome)
                return outcome
            if ckpt is None:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=0,
                    failure_class=FailureClass.STATE_CORRUPTION.value,
                    error=f"no checkpoint found for run_id={rid}",
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                self._emit_end(rid, outcome)
                return outcome
            start_index = max(0, ckpt.next_step - 1)
            tool_results = list(ckpt.tool_results)
            tokens_in = ckpt.tokens_in
            tokens_out = ckpt.tokens_out
            resumed = True

        if self.trace:
            self.trace.emit(
                TraceEvent(
                    run_id=rid,
                    event_type=EventType.RUN_START,
                    metadata={
                        "model": self.config.model,
                        "plan_len": len(plan),
                        "resume": resumed,
                        "start_step": start_index + 1,
                        "crash_after_step": crash_after_step,
                    },
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

        for i in range(start_index + 1, len(plan) + 1):
            step = plan[i - 1]
            if self.trace:
                self.trace.emit(
                    TraceEvent(
                        run_id=rid,
                        event_type=EventType.STEP_START,
                        step=i,
                        tool_name=step.tool,
                    )
                )

            # Policy check before tool execution (no side effects on deny)
            decision = self.policy.check(step.tool, step.args)
            if not decision.allowed:
                if self.trace:
                    self.trace.emit(
                        TraceEvent(
                            run_id=rid,
                            event_type=EventType.ERROR,
                            step=i,
                            tool_name=step.tool,
                            error=decision.reason,
                            failure_class=FailureClass.POLICY_VIOLATION.value,
                        )
                    )
                tool_results.append(
                    {
                        "step": i,
                        "tool": step.tool,
                        "ok": False,
                        "output": None,
                        "error": decision.reason,
                        "failure_class": FailureClass.POLICY_VIOLATION.value,
                        "attempt": 0,
                        "cached": False,
                        "policy_blocked": True,
                    }
                )
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=i,
                    failure_class=FailureClass.POLICY_VIOLATION.value,
                    error=decision.reason,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=self._cost(tokens_in, tokens_out),
                    tool_results=tool_results,
                    metadata={"resumed": resumed},
                )
                self._emit_end(rid, outcome)
                return outcome

            # Accrue mock tokens before the call (budget is a first-class gate)
            tokens_in += self.config.tokens_per_step
            tokens_out += self.config.tokens_per_step // 2
            budget_fail = self._budget_failure(tokens_in, tokens_out)
            if budget_fail is not None:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=i - 1,
                    failure_class=FailureClass.BUDGET_EXCEEDED.value,
                    error=budget_fail,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=self._cost(tokens_in, tokens_out),
                    tool_results=tool_results,
                    metadata={"resumed": resumed},
                )
                if self.trace:
                    self.trace.emit(
                        TraceEvent(
                            run_id=rid,
                            event_type=EventType.ERROR,
                            step=i,
                            error=budget_fail,
                            failure_class=FailureClass.BUDGET_EXCEEDED.value,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            cost_usd=outcome.cost_usd,
                        )
                    )
                self._emit_end(rid, outcome)
                return outcome

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

            if self.state_store is not None:
                self.state_store.save(
                    Checkpoint(
                        run_id=rid,
                        next_step=i + 1,
                        tool_results=tool_results,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        metadata={"last_tool": step.tool},
                    )
                )

            if crash_after_step is not None and i >= crash_after_step:
                # Checkpoint already saved above. Raise so callers must resume
                # from the store — mirrors a process death more closely than a
                # cooperative RunOutcome return.
                err = f"injected crash after step {i}"
                if self.trace:
                    self.trace.emit(
                        TraceEvent(
                            run_id=rid,
                            event_type=EventType.ERROR,
                            step=i,
                            error=err,
                            metadata={"injected_crash": True},
                        )
                    )
                raise InjectedCrash(err)

            if not result.ok and step.required:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=i,
                    failure_class=result.failure_class or FailureClass.UNKNOWN.value,
                    error=result.error,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=self._cost(tokens_in, tokens_out),
                    tool_results=tool_results,
                    metadata={"resumed": resumed},
                )
                self._emit_end(rid, outcome)
                return outcome

        outcome = RunOutcome(
            run_id=rid,
            ok=True,
            steps_completed=len(plan),
            latency_ms=(time.perf_counter() - started) * 1000,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=self._cost(tokens_in, tokens_out),
            tool_results=tool_results,
            metadata={"resumed": resumed},
        )
        self._emit_end(rid, outcome)
        return outcome

    def run_reactive(
        self,
        planner: Callable[[list[dict[str, Any]]], ToolPlanStep | None],
        *,
        run_id: str | None = None,
        resume: bool = False,
        crash_after_step: int | None = None,
    ) -> RunOutcome:
        """Build the plan step-by-step from real tool results (rule-based loop).

        planner(tool_results_so_far) -> next ToolPlanStep, or None to stop.
        T1/T2 use this so write contents come from prior tool outputs, not from
        copying expected fixtures inside build_plan().
        """
        rid = run_id or str(uuid.uuid4())
        return self._run_reactive_loop(
            planner, run_id=rid, resume=resume, crash_after_step=crash_after_step
        )

    def _run_reactive_loop(
        self,
        planner: Callable[[list[dict[str, Any]]], ToolPlanStep | None],
        *,
        run_id: str,
        resume: bool = False,
        crash_after_step: int | None = None,
    ) -> RunOutcome:
        """Execute planner-driven steps one at a time with real tool results."""
        rid = run_id
        started = time.perf_counter()
        tokens_in = 0
        tokens_out = 0
        tool_results: list[dict[str, Any]] = []
        resumed = False
        start_step_number = 1  # 1-based

        if resume and self.state_store is not None:
            try:
                ckpt = self.state_store.load(rid)
            except StateCorruptionError as exc:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=0,
                    failure_class=FailureClass.STATE_CORRUPTION.value,
                    error=str(exc),
                    latency_ms=(time.perf_counter() - started) * 1000,
                    metadata={"resume_attempted": True},
                )
                self._emit_end(rid, outcome)
                return outcome
            if ckpt is None:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=0,
                    failure_class=FailureClass.STATE_CORRUPTION.value,
                    error=f"no checkpoint found for run_id={rid}",
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                self._emit_end(rid, outcome)
                return outcome
            tool_results = list(ckpt.tool_results)
            tokens_in = ckpt.tokens_in
            tokens_out = ckpt.tokens_out
            start_step_number = ckpt.next_step
            resumed = True

        if self.trace:
            self.trace.emit(
                TraceEvent(
                    run_id=rid,
                    event_type=EventType.RUN_START,
                    metadata={
                        "model": self.config.model,
                        "reactive": True,
                        "resume": resumed,
                        "start_step": start_step_number,
                        "crash_after_step": crash_after_step,
                    },
                )
            )

        i = start_step_number
        while i <= self.config.max_steps:
            step = planner(tool_results)
            if step is None:
                break

            if self.trace:
                self.trace.emit(
                    TraceEvent(
                        run_id=rid,
                        event_type=EventType.STEP_START,
                        step=i,
                        tool_name=step.tool,
                    )
                )

            decision = self.policy.check(step.tool, step.args)
            if not decision.allowed:
                if self.trace:
                    self.trace.emit(
                        TraceEvent(
                            run_id=rid,
                            event_type=EventType.ERROR,
                            step=i,
                            tool_name=step.tool,
                            error=decision.reason,
                            failure_class=FailureClass.POLICY_VIOLATION.value,
                        )
                    )
                tool_results.append(
                    {
                        "step": i,
                        "tool": step.tool,
                        "ok": False,
                        "output": None,
                        "error": decision.reason,
                        "failure_class": FailureClass.POLICY_VIOLATION.value,
                        "attempt": 0,
                        "cached": False,
                        "policy_blocked": True,
                    }
                )
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=i,
                    failure_class=FailureClass.POLICY_VIOLATION.value,
                    error=decision.reason,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=self._cost(tokens_in, tokens_out),
                    tool_results=tool_results,
                    metadata={"resumed": resumed, "reactive": True},
                )
                self._emit_end(rid, outcome)
                return outcome

            tokens_in += self.config.tokens_per_step
            tokens_out += self.config.tokens_per_step // 2
            budget_fail = self._budget_failure(tokens_in, tokens_out)
            if budget_fail is not None:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=i - 1,
                    failure_class=FailureClass.BUDGET_EXCEEDED.value,
                    error=budget_fail,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=self._cost(tokens_in, tokens_out),
                    tool_results=tool_results,
                    metadata={"resumed": resumed, "reactive": True},
                )
                if self.trace:
                    self.trace.emit(
                        TraceEvent(
                            run_id=rid,
                            event_type=EventType.ERROR,
                            step=i,
                            error=budget_fail,
                            failure_class=FailureClass.BUDGET_EXCEEDED.value,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            cost_usd=outcome.cost_usd,
                        )
                    )
                self._emit_end(rid, outcome)
                return outcome

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

            if self.state_store is not None:
                self.state_store.save(
                    Checkpoint(
                        run_id=rid,
                        next_step=i + 1,
                        tool_results=tool_results,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        metadata={"last_tool": step.tool, "reactive": True},
                    )
                )

            if crash_after_step is not None and i >= crash_after_step:
                err = f"injected crash after step {i}"
                if self.trace:
                    self.trace.emit(
                        TraceEvent(
                            run_id=rid,
                            event_type=EventType.ERROR,
                            step=i,
                            error=err,
                            metadata={"injected_crash": True},
                        )
                    )
                raise InjectedCrash(err)

            if not result.ok and step.required:
                outcome = RunOutcome(
                    run_id=rid,
                    ok=False,
                    steps_completed=i,
                    failure_class=result.failure_class or FailureClass.UNKNOWN.value,
                    error=result.error,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=self._cost(tokens_in, tokens_out),
                    tool_results=tool_results,
                    metadata={"resumed": resumed, "reactive": True},
                )
                self._emit_end(rid, outcome)
                return outcome

            i += 1
        else:
            outcome = RunOutcome(
                run_id=rid,
                ok=False,
                steps_completed=len(tool_results),
                failure_class=FailureClass.INVALID_STRUCTURED_OUTPUT.value,
                error=f"reactive plan exceeded max_steps {self.config.max_steps}",
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=self._cost(tokens_in, tokens_out),
                tool_results=tool_results,
                metadata={"resumed": resumed, "reactive": True},
            )
            self._emit_end(rid, outcome)
            return outcome

        outcome = RunOutcome(
            run_id=rid,
            ok=True,
            steps_completed=len(tool_results),
            latency_ms=(time.perf_counter() - started) * 1000,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=self._cost(tokens_in, tokens_out),
            tool_results=tool_results,
            metadata={"resumed": resumed, "reactive": True},
        )
        self._emit_end(rid, outcome)
        return outcome

    def _cost(self, tokens_in: int, tokens_out: int) -> float:
        return ((tokens_in + tokens_out) / 1000.0) * self.config.cost_per_1k_tokens

    def _budget_failure(self, tokens_in: int, tokens_out: int) -> str | None:
        total = tokens_in + tokens_out
        if self.config.max_tokens is not None and total > self.config.max_tokens:
            return (
                f"token budget exceeded: {total} > {self.config.max_tokens}"
            )
        cost = self._cost(tokens_in, tokens_out)
        if self.config.max_cost_usd is not None and cost > self.config.max_cost_usd:
            return (
                f"cost budget exceeded: {cost:.6f} > {self.config.max_cost_usd}"
            )
        return None

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
                metadata={
                    "ok": outcome.ok,
                    "steps_completed": outcome.steps_completed,
                    **outcome.metadata,
                },
            )
        )
