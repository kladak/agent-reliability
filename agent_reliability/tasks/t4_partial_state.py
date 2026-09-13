"""T4: checkpoint-resume simulation via injected mid-run crash.

This is a harness demo, not a real OS process death. The runtime raises
InjectedCrash after persisting a checkpoint; execute() catches it and
resumes from the state store on the same ToolRouter (in-memory idempotency
cache is intentionally shared for this simulation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.observe.trace import EventType, read_trace
from agent_reliability.runtime.mock_agent import InjectedCrash, RunOutcome, ToolPlanStep
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext


class T4PartialState(BaseTask):
    task_id = "T4_partial_state"
    description = (
        "Checkpoint-resume simulation: InjectedCrash after step 1, then resume from store"
    )

    FINAL_PATH = "final.txt"
    FINAL_CONTENT = "checkpoint-resume-ok\n"

    def setup(self, ctx: TaskContext) -> None:
        ctx.workspace.mkdir(parents=True, exist_ok=True)
        (ctx.workspace / "state").mkdir(parents=True, exist_ok=True)

    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        return [
            ToolPlanStep(
                tool="fs_write",
                args={"path": "step1.txt", "content": "one\n"},
                idempotency_key=f"t4-s1-{ctx.run_id}",
            ),
            ToolPlanStep(
                tool="fs_write",
                args={"path": "step2.txt", "content": "two\n"},
                idempotency_key=f"t4-s2-{ctx.run_id}",
            ),
            ToolPlanStep(
                tool="fs_write",
                args={"path": self.FINAL_PATH, "content": self.FINAL_CONTENT},
                idempotency_key=f"t4-final-{ctx.run_id}",
            ),
        ]

    def execute(
        self,
        ctx: TaskContext,
        *,
        agent: Any,
        plan: list[ToolPlanStep],
        trace_path: Path | None = None,
    ) -> RunOutcome:
        if trace_path is not None:
            (ctx.workspace / ".trace_path").write_text(str(trace_path), encoding="utf-8")

        try:
            return agent.run(plan, run_id=ctx.run_id, crash_after_step=1)
        except InjectedCrash:
            outcome = agent.run(plan, run_id=ctx.run_id, resume=True)
            outcome.metadata["prior_crash"] = True
            store = agent.state_store
            if store is not None:
                ckpt = store.load(ctx.run_id)
                outcome.metadata["checkpoint_after_resume"] = (
                    ckpt.model_dump() if ckpt else None
                )
            return outcome

    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        checks: list[dict] = []
        final = ctx.workspace / self.FINAL_PATH
        step1 = ctx.workspace / "step1.txt"

        checks.append({"name": "step1_survived_crash", "passed": step1.exists()})
        checks.append(
            {
                "name": "final_artifact_written",
                "passed": final.exists()
                and final.read_text(encoding="utf-8") == self.FINAL_CONTENT,
            }
        )
        checks.append({"name": "run_ok_after_resume", "passed": outcome.ok is True})
        checks.append(
            {
                "name": "resume_metadata",
                "passed": bool(outcome.metadata.get("resumed"))
                and bool(outcome.metadata.get("prior_crash")),
            }
        )

        trace_hint = ctx.workspace / ".trace_path"
        if trace_hint.exists():
            events = read_trace(trace_hint.read_text().strip())
            resumes = [
                e
                for e in events
                if e.event_type == EventType.RUN_START
                and (e.metadata or {}).get("resume") is True
            ]
            checks.append({"name": "trace_shows_resume", "passed": len(resumes) >= 1})

        passed = all(c["passed"] for c in checks) and outcome.ok
        if not passed:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="T4 assertions failed",
            )
        return GradeResult(passed=True, checks=checks, message="T4 passed")
