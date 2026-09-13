"""T3: complete work despite a flaky tool (injected failures)."""

from __future__ import annotations

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.runtime.mock_agent import RunOutcome, ToolPlanStep
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext


class T3FlakyTool(BaseTask):
    task_id = "T3_flaky_tool"
    description = "Complete work despite a flaky tool (injected failures)"

    MESSAGE = "reliability-ok"
    FAIL_TIMES = 2

    def setup(self, ctx: TaskContext) -> None:
        # Reset flaky counter so each eval run is deterministic
        from agent_reliability.tools.flaky_echo import FlakyEchoTool

        FlakyEchoTool.reset()
        ctx.workspace.mkdir(parents=True, exist_ok=True)

    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        return [
            ToolPlanStep(
                tool="flaky_echo",
                args={"message": self.MESSAGE, "fail_times": self.FAIL_TIMES},
                required=True,
            ),
            ToolPlanStep(
                tool="fs_write",
                args={
                    "path": "flaky_result.txt",
                    "content": f"{self.MESSAGE}\n",
                },
                idempotency_key=f"t3-result-{ctx.run_id}",
            ),
        ]

    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        checks: list[dict] = []

        echo_steps = [r for r in outcome.tool_results if r.get("tool") == "flaky_echo"]
        echo_ok = bool(echo_steps) and echo_steps[0].get("ok") is True
        checks.append(
            {
                "name": "flaky_echo_succeeded",
                "passed": echo_ok,
                "attempts": echo_steps[0].get("attempt") if echo_steps else None,
            }
        )

        # Retries should have happened (attempt > 1) given FAIL_TIMES=2
        retried = echo_ok and (echo_steps[0].get("attempt") or 0) > 1
        checks.append({"name": "retries_observed", "passed": retried})

        result_path = ctx.workspace / "flaky_result.txt"
        file_ok = result_path.exists() and result_path.read_text() == f"{self.MESSAGE}\n"
        checks.append({"name": "result_file_written", "passed": file_ok})

        if not (echo_ok and retried and file_ok and outcome.ok):
            fc = outcome.failure_class or FailureClass.TASK_ASSERTION_FAILED.value
            if outcome.ok and not (echo_ok and retried and file_ok):
                fc = FailureClass.TASK_ASSERTION_FAILED.value
            return GradeResult(
                passed=False,
                failure_class=fc,
                checks=checks,
                message="T3 assertions failed",
            )

        return GradeResult(passed=True, checks=checks, message="T3 passed")
