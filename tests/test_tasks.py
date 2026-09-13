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


def test_t1_grader_rejects_invalid_json(tmp_path: Path) -> None:
    from agent_reliability.runtime.mock_agent import RunOutcome
    from agent_reliability.tasks.t1_file_repair import T1FileRepair

    task = T1FileRepair()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "config.json").write_text("{not json", encoding="utf-8")
    ctx = TaskContext(
        workspace=workspace,
        fixtures_dir=Path("fixtures") / task.task_id,
        run_id="neg-t1",
    )
    outcome = RunOutcome(
        run_id="neg-t1",
        ok=True,
        steps_completed=1,
        latency_ms=1.0,
        tool_results=[
            {
                "step": 1,
                "tool": "fs_read",
                "ok": True,
                "output": {"path": "config.json", "content": "{broken"},
                "cached": False,
            }
        ],
    )
    grade = task.grade(ctx, outcome)
    assert not grade.passed
    assert grade.failure_class == "task_assertion_failed"
    by_name = {c["name"]: c for c in grade.checks}
    assert by_name["valid_json"]["passed"] is False


def test_t1_grader_rejects_skipping_fs_read(tmp_path: Path) -> None:
    from agent_reliability.runtime.mock_agent import RunOutcome
    from agent_reliability.tasks.t1_file_repair import T1FileRepair

    task = T1FileRepair()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    # Plant a valid-looking file without any read in the outcome
    import json

    (workspace / "config.json").write_text(
        json.dumps(
            {
                "name": "demo-service",
                "port": 8080,
                "enabled": True,
                "tags": ["alpha", "beta"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ctx = TaskContext(
        workspace=workspace,
        fixtures_dir=Path("fixtures") / task.task_id,
        run_id="neg-t1-skip",
    )
    outcome = RunOutcome(
        run_id="neg-t1-skip",
        ok=True,
        steps_completed=1,
        latency_ms=1.0,
        tool_results=[
            {
                "step": 1,
                "tool": "fs_write",
                "ok": True,
                "output": {"path": "config.json"},
                "cached": False,
            }
        ],
    )
    grade = task.grade(ctx, outcome)
    assert not grade.passed
    assert any(c["name"] == "fs_read_used" and not c["passed"] for c in grade.checks)


def test_t2_grader_rejects_wrong_report(tmp_path: Path) -> None:
    from agent_reliability.runtime.mock_agent import RunOutcome
    from agent_reliability.tasks.t2_api_reconcile import T2ApiReconcile

    task = T2ApiReconcile()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "reconcile_report.json").write_text(
        '{"only_in_a": [], "only_in_b": [], "qty_mismatch": [], "matched": []}\n',
        encoding="utf-8",
    )
    ctx = TaskContext(
        workspace=workspace,
        fixtures_dir=Path("fixtures") / task.task_id,
        run_id="neg-t2",
    )
    # HTTP happened, but report does not match reconcile(bodies)
    body_a = [{"id": "sku-1", "qty": 10}, {"id": "sku-2", "qty": 3}, {"id": "sku-3", "qty": 7}]
    body_b = [{"id": "sku-2", "qty": 3}, {"id": "sku-3", "qty": 5}, {"id": "sku-4", "qty": 1}]
    outcome = RunOutcome(
        run_id="neg-t2",
        ok=True,
        steps_completed=3,
        latency_ms=1.0,
        tool_results=[
            {
                "step": 1,
                "tool": "http_get",
                "ok": True,
                "output": {"path": "/inventory/a", "status": 200, "body": body_a},
            },
            {
                "step": 2,
                "tool": "http_get",
                "ok": True,
                "output": {"path": "/inventory/b", "status": 200, "body": body_b},
            },
            {
                "step": 3,
                "tool": "fs_write",
                "ok": True,
                "output": {"path": "reconcile_report.json"},
            },
        ],
    )
    grade = task.grade(ctx, outcome)
    assert not grade.passed
    by_name = {c["name"]: c for c in grade.checks}
    assert by_name["report_matches_expected"]["passed"] is False
