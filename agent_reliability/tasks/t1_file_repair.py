"""T1: repair broken JSON config and write a valid file."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.runtime.mock_agent import RunOutcome, ToolPlanStep
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "T1_file_repair"


class T1FileRepair(BaseTask):
    task_id = "T1_file_repair"
    description = "Fix a broken JSON config and write a valid file"

    def setup(self, ctx: TaskContext) -> None:
        src = FIXTURES / "broken_config.json"
        dest = ctx.workspace / "config.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)

    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        expected = (FIXTURES / "expected_config.json").read_text(encoding="utf-8")
        # Normalize to compact-but-valid JSON the grader accepts
        repaired = json.dumps(json.loads(expected), indent=2) + "\n"
        return [
            ToolPlanStep(tool="fs_read", args={"path": "config.json"}),
            ToolPlanStep(
                tool="fs_write",
                args={"path": "config.json", "content": repaired},
                idempotency_key=f"t1-write-{ctx.run_id}",
            ),
            # Second write with same key should be idempotent / cached
            ToolPlanStep(
                tool="fs_write",
                args={"path": "config.json", "content": repaired},
                idempotency_key=f"t1-write-{ctx.run_id}",
            ),
        ]

    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        checks: list[dict] = []
        path = ctx.workspace / "config.json"

        exists = path.exists()
        checks.append({"name": "config_exists", "passed": exists})
        if not exists:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="config.json missing after run",
            )

        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
            checks.append({"name": "valid_json", "passed": True})
        except json.JSONDecodeError as exc:
            checks.append({"name": "valid_json", "passed": False, "error": str(exc)})
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="config.json is not valid JSON",
            )

        expected = json.loads((FIXTURES / "expected_config.json").read_text())
        match = data == expected
        checks.append({"name": "matches_expected", "passed": match, "got": data})
        if not match:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="config.json does not match expected structure",
            )

        # Idempotency: at least one write should have been cached on retry
        cached_writes = [
            r
            for r in outcome.tool_results
            if r.get("tool") == "fs_write" and r.get("cached")
        ]
        checks.append(
            {
                "name": "idempotent_write_observed",
                "passed": len(cached_writes) >= 1,
                "cached_count": len(cached_writes),
            }
        )
        if not cached_writes:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="expected idempotent cached fs_write on repeated key",
            )

        if not outcome.ok:
            return GradeResult(
                passed=False,
                failure_class=outcome.failure_class or FailureClass.UNKNOWN.value,
                checks=checks,
                message=outcome.error or "runtime reported failure",
            )

        return GradeResult(passed=True, checks=checks, message="T1 passed")
