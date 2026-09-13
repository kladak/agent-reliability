"""T6: finish under a token/cost budget (or fail with budget_exceeded)."""

from __future__ import annotations

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.runtime.mock_agent import MockAgentConfig, RunOutcome, ToolPlanStep
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext


class T6CostBudget(BaseTask):
    task_id = "T6_cost_budget"
    description = "Finish under a token/cost budget or fail with taxonomy"

    # 2 steps * (50 in + 25 out) = 150 tokens total with default config
    EXPECTED_STEPS = 2

    def setup(self, ctx: TaskContext) -> None:
        ctx.workspace.mkdir(parents=True, exist_ok=True)

    def agent_config(self) -> MockAgentConfig:
        """Budget sized to allow exactly the golden plan (measured tokens)."""
        return MockAgentConfig(
            model="mock",
            tokens_per_step=50,
            cost_per_1k_tokens=0.01,
            max_tokens=150,  # 2 steps * 75 = 150; third step would exceed
            max_cost_usd=0.01,
        )

    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        return [
            ToolPlanStep(
                tool="fs_write",
                args={"path": "budget_a.txt", "content": "a\n"},
                idempotency_key=f"t6-a-{ctx.run_id}",
            ),
            ToolPlanStep(
                tool="fs_write",
                args={"path": "budget_b.txt", "content": "b\n"},
                idempotency_key=f"t6-b-{ctx.run_id}",
            ),
        ]

    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        checks: list[dict] = []
        a = ctx.workspace / "budget_a.txt"
        b = ctx.workspace / "budget_b.txt"

        checks.append({"name": "artifact_a", "passed": a.exists()})
        checks.append({"name": "artifact_b", "passed": b.exists()})
        checks.append({"name": "run_ok", "passed": outcome.ok})

        total_tokens = outcome.tokens_in + outcome.tokens_out
        under_tokens = total_tokens <= 150
        checks.append(
            {
                "name": "under_token_budget",
                "passed": under_tokens,
                "tokens_in": outcome.tokens_in,
                "tokens_out": outcome.tokens_out,
                "total": total_tokens,
                "max_tokens": 150,
            }
        )
        under_cost = outcome.cost_usd <= 0.01
        checks.append(
            {
                "name": "under_cost_budget",
                "passed": under_cost,
                "cost_usd": outcome.cost_usd,
                "max_cost_usd": 0.01,
            }
        )

        if not (outcome.ok and a.exists() and b.exists() and under_tokens and under_cost):
            return GradeResult(
                passed=False,
                failure_class=(
                    outcome.failure_class
                    if not outcome.ok
                    else FailureClass.TASK_ASSERTION_FAILED.value
                ),
                checks=checks,
                message="T6 budget assertions failed",
            )
        return GradeResult(passed=True, checks=checks, message="T6 passed")
