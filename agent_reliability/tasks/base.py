"""Task definition and grade result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_reliability.runtime.mock_agent import RunOutcome, ToolPlanStep


class GradeResult(BaseModel):
    passed: bool
    failure_class: str | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class TaskContext(BaseModel):
    workspace: Path
    fixtures_dir: Path
    run_id: str

    model_config = {"arbitrary_types_allowed": True}


class BaseTask(ABC):
    task_id: str
    description: str

    @abstractmethod
    def setup(self, ctx: TaskContext) -> None:
        """Prepare workspace fixtures for a run."""

    @abstractmethod
    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        """Return the mock agent plan that should solve this task."""

    @abstractmethod
    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        """Deterministic grader over workspace + run outcome."""
