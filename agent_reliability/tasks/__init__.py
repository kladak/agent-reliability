from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext
from agent_reliability.tasks.t1_file_repair import T1FileRepair
from agent_reliability.tasks.t3_flaky_tool import T3FlakyTool

TASK_REGISTRY: dict[str, type[BaseTask]] = {
    T1FileRepair.task_id: T1FileRepair,
    T3FlakyTool.task_id: T3FlakyTool,
}


def get_task(task_id: str) -> BaseTask:
    cls = TASK_REGISTRY.get(task_id)
    if cls is None:
        raise KeyError(f"unknown task: {task_id}")
    return cls()


__all__ = [
    "BaseTask",
    "GradeResult",
    "TaskContext",
    "T1FileRepair",
    "T3FlakyTool",
    "TASK_REGISTRY",
    "get_task",
]
