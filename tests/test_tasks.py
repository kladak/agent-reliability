import tempfile
import uuid
from pathlib import Path

from agent_reliability.runtime import MockAgentRuntime
from agent_reliability.tasks import get_task
from agent_reliability.tasks.base import TaskContext
from agent_reliability.tools import FlakyEchoTool, FsReadTool, FsWriteTool, ToolRouter


def _run_task(task_id: str):
    task = get_task(task_id)
    run_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        ctx = TaskContext(workspace=workspace, fixtures_dir=Path("fixtures") / task_id, run_id=run_id)
        task.setup(ctx)
        FlakyEchoTool.reset()
        router = ToolRouter(
            [FsReadTool(workspace), FsWriteTool(workspace), FlakyEchoTool(max_retries=5)],
            run_id=run_id,
        )
        agent = MockAgentRuntime(router)
        outcome = agent.run(task.build_plan(ctx), run_id=run_id)
        grade = task.grade(ctx, outcome)
        return outcome, grade


def test_t1_file_repair_passes() -> None:
    outcome, grade = _run_task("T1_file_repair")
    assert outcome.ok
    assert grade.passed, grade.message


def test_t3_flaky_tool_passes() -> None:
    outcome, grade = _run_task("T3_flaky_tool")
    assert outcome.ok
    assert grade.passed, grade.message
