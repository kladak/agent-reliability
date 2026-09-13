import tempfile
import uuid
from pathlib import Path

from agent_reliability.runtime import MockAgentConfig, MockAgentRuntime, StateStore
from agent_reliability.tasks import TASK_REGISTRY, get_task
from agent_reliability.tasks.base import TaskContext
from agent_reliability.tools import (
    FlakyEchoTool,
    FsReadTool,
    FsWriteTool,
    MockHttpTool,
    ToolRouter,
)


def _run_task(task_id: str):
    task = get_task(task_id)
    run_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        ctx = TaskContext(
            workspace=workspace,
            fixtures_dir=Path("fixtures") / task_id,
            run_id=run_id,
        )
        task.setup(ctx)
        FlakyEchoTool.reset()
        tools = [
            FsReadTool(workspace),
            FsWriteTool(workspace),
            FlakyEchoTool(max_retries=5),
            *task.extra_tools(ctx),
        ]
        router = ToolRouter(tools, run_id=run_id)
        agent = MockAgentRuntime(
            router,
            config=task.agent_config(),
            state_store=StateStore(workspace / "state"),
            policy=task.policy(),
        )
        plan = task.build_plan(ctx)
        outcome = task.execute(ctx, agent=agent, plan=plan, trace_path=None)
        grade = task.grade(ctx, outcome)
        return outcome, grade


def test_all_registered_tasks_pass() -> None:
    assert set(TASK_REGISTRY) == {
        "T1_file_repair",
        "T2_api_reconcile",
        "T3_flaky_tool",
        "T4_partial_state",
        "T5_policy_refusal",
        "T6_cost_budget",
    }
    for task_id in sorted(TASK_REGISTRY):
        outcome, grade = _run_task(task_id)
        assert grade.passed, f"{task_id}: {grade.message} checks={grade.checks}"


def test_budget_exceeded_taxonomy() -> None:
    """Tight budget must fail with budget_exceeded (not a golden-suite pass)."""
    from agent_reliability.tasks.t6_cost_budget import T6CostBudget

    task = T6CostBudget()
    run_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        ctx = TaskContext(
            workspace=workspace, fixtures_dir=Path("fixtures") / task.task_id, run_id=run_id
        )
        task.setup(ctx)
        router = ToolRouter(
            [FsReadTool(workspace), FsWriteTool(workspace)], run_id=run_id
        )
        agent = MockAgentRuntime(
            router,
            config=MockAgentConfig(
                tokens_per_step=50,
                cost_per_1k_tokens=0.01,
                max_tokens=10,  # first step alone is 75 tokens
            ),
            policy=task.policy(),
        )
        outcome = agent.run(task.build_plan(ctx), run_id=run_id)
        assert not outcome.ok
        assert outcome.failure_class == "budget_exceeded"
        assert not (workspace / "budget_a.txt").exists()
