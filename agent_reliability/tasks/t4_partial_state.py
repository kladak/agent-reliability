"""T4: resume after mid-run crash using persisted checkpoints."""

from __future__ import annotations

from pathlib import Path

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.observe.trace import EventType, read_trace
from agent_reliability.runtime.mock_agent import (
    MockAgentConfig,
    MockAgentRuntime,
    RunOutcome,
    ToolPlanStep,
)
from agent_reliability.runtime.state_store import StateStore
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext
from agent_reliability.tools.filesystem import FsReadTool, FsWriteTool
from agent_reliability.tools.router import ToolRouter


class T4PartialState(BaseTask):
    task_id = "T4_partial_state"
    description = "Resume after mid-run crash using persisted state"

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

    def run_with_crash_and_resume(
        self,
        ctx: TaskContext,
        *,
        trace_path: Path | None = None,
    ) -> RunOutcome:
        """Helper used by eval/tests: crash after step 1, then resume."""
        from agent_reliability.observe.trace import TraceSink

        store = StateStore(ctx.workspace / "state")
        plan = self.build_plan(ctx)
        tools = [FsReadTool(ctx.workspace), FsWriteTool(ctx.workspace)]

        if trace_path is not None:
            sink = TraceSink(trace_path)
            (ctx.workspace / ".trace_path").write_text(str(trace_path), encoding="utf-8")
        else:
            sink = None

        try:
            router = ToolRouter(tools, trace=sink, run_id=ctx.run_id)
            agent = MockAgentRuntime(
                router,
                trace=sink,
                config=MockAgentConfig(model="mock"),
                state_store=store,
            )
            crashed = agent.run(plan, run_id=ctx.run_id, crash_after_step=1)
            assert crashed.metadata.get("crashed") is True
            # Resume — same run_id, continue from checkpoint
            outcome = agent.run(plan, run_id=ctx.run_id, resume=True)
            outcome.metadata["prior_crash"] = True
            outcome.metadata["checkpoint_after_crash"] = (
                store.load(ctx.run_id).model_dump() if store.load(ctx.run_id) else None
            )
            return outcome
        finally:
            if sink is not None:
                sink.close()


    def execute(self, ctx: TaskContext, *, agent, plan, trace_path=None):
        # Ignore the pre-built agent; we need state_store + crash/resume semantics.
        return self.run_with_crash_and_resume(ctx, trace_path=trace_path)

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
        checks.append(
            {
                "name": "run_ok_after_resume",
                "passed": outcome.ok is True,
            }
        )
        checks.append(
            {
                "name": "resume_metadata",
                "passed": bool(outcome.metadata.get("resumed"))
                or bool(outcome.metadata.get("prior_crash")),
            }
        )

        # Replay-friendly: if a trace path was attached on ctx via metadata file
        trace_hint = ctx.workspace / ".trace_path"
        if trace_hint.exists():
            events = read_trace(trace_hint.read_text().strip())
            resumes = [
                e
                for e in events
                if e.event_type == EventType.RUN_START
                and (e.metadata or {}).get("resume") is True
            ]
            checks.append(
                {"name": "trace_shows_resume", "passed": len(resumes) >= 1}
            )

        passed = all(c["passed"] for c in checks) and outcome.ok
        if not passed:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="T4 assertions failed",
            )
        return GradeResult(passed=True, checks=checks, message="T4 passed")
