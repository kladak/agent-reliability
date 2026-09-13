from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext
from agent_reliability.tasks.t1_file_repair import T1FileRepair
from agent_reliability.tasks.t2_api_reconcile import T2ApiReconcile
from agent_reliability.tasks.t3_flaky_tool import T3FlakyTool
from agent_reliability.tasks.t4_partial_state import T4PartialState
from agent_reliability.tasks.t5_policy_refusal import T5PolicyRefusal
from agent_reliability.tasks.t6_cost_budget import T6CostBudget

TASK_REGISTRY: dict[str, type[BaseTask]] = {
    T1FileRepair.task_id: T1FileRepair,
    T2ApiReconcile.task_id: T2ApiReconcile,
    T3FlakyTool.task_id: T3FlakyTool,
    T4PartialState.task_id: T4PartialState,
    T5PolicyRefusal.task_id: T5PolicyRefusal,
    T6CostBudget.task_id: T6CostBudget,
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
    "T2ApiReconcile",
    "T3FlakyTool",
    "T4PartialState",
    "T5PolicyRefusal",
    "T6CostBudget",
    "TASK_REGISTRY",
    "get_task",
]
