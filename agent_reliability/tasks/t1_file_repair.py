"""T1: repair broken JSON config via fs_read → repair → fs_write.

The mock agent does not copy expected_config.json. Write contents are derived
from the fs_read tool output by a small rule-based repair of common JSON
breakage (e.g. missing ']'). Skipping the read leaves nothing to repair.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.runtime.mock_agent import RunOutcome, ToolPlanStep
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "T1_file_repair"


def repair_broken_config(raw: str) -> str:
    """Repair fixture-style broken JSON without consulting expected_*.json.

    Strategy: try parse; if that fails, insert missing closers (']', '}') until
    parse succeeds (bounded). Normalize to indented JSON.
    """
    try:
        data = json.loads(raw)
        return json.dumps(data, indent=2) + "\n"
    except json.JSONDecodeError:
        pass

    candidate = raw.rstrip()
    # Prefer inserting a missing ] before the final } (T1 fixture shape).
    if candidate.endswith("}"):
        trial = candidate[:-1].rstrip() + "\n  ]\n}\n"
        try:
            data = json.loads(trial)
            return json.dumps(data, indent=2) + "\n"
        except json.JSONDecodeError:
            pass

    closers = ["]", "}", "]}", "]]", "]]}"]
    for closer in closers:
        try:
            data = json.loads(candidate + closer)
            return json.dumps(data, indent=2) + "\n"
        except json.JSONDecodeError:
            continue

    raise ValueError("unable to repair broken JSON config from tool read")


class T1FileRepair(BaseTask):
    task_id = "T1_file_repair"
    description = "Fix a broken JSON config and write a valid file"

    def setup(self, ctx: TaskContext) -> None:
        src = FIXTURES / "broken_config.json"
        dest = ctx.workspace / "config.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)

    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        # Skeleton only; execute() uses a reactive planner that fills writes
        # from fs_read output. No expected_config.json copy here.
        return [
            ToolPlanStep(tool="fs_read", args={"path": "config.json"}),
            ToolPlanStep(
                tool="fs_write",
                args={"path": "config.json", "content": "<derived-from-fs_read>"},
                idempotency_key=f"t1-write-{ctx.run_id}",
            ),
            ToolPlanStep(
                tool="fs_write",
                args={"path": "config.json", "content": "<derived-from-fs_read>"},
                idempotency_key=f"t1-write-{ctx.run_id}",
            ),
        ]

    def execute(
        self,
        ctx: TaskContext,
        *,
        agent: Any,
        plan: list[ToolPlanStep],
        trace_path: Path | None = None,
    ) -> RunOutcome:
        write_key = f"t1-write-{ctx.run_id}"
        repaired_holder: dict[str, str | None] = {"content": None}

        def planner(results: list[dict[str, Any]]) -> ToolPlanStep | None:
            if not results:
                return ToolPlanStep(tool="fs_read", args={"path": "config.json"})

            if repaired_holder["content"] is None:
                read = next(
                    (
                        r
                        for r in results
                        if r.get("tool") == "fs_read" and r.get("ok")
                    ),
                    None,
                )
                if read is None:
                    return None
                raw = (read.get("output") or {}).get("content")
                if raw is None:
                    return None
                repaired_holder["content"] = repair_broken_config(raw)

            writes = [r for r in results if r.get("tool") == "fs_write"]
            if len(writes) < 2:
                return ToolPlanStep(
                    tool="fs_write",
                    args={
                        "path": "config.json",
                        "content": repaired_holder["content"],
                    },
                    idempotency_key=write_key,
                )
            return None

        return agent.run_reactive(planner, run_id=ctx.run_id)

    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        checks: list[dict] = []
        path = ctx.workspace / "config.json"

        reads = [
            r
            for r in outcome.tool_results
            if r.get("tool") == "fs_read" and r.get("ok")
        ]
        checks.append(
            {
                "name": "fs_read_used",
                "passed": len(reads) >= 1,
                "read_count": len(reads),
            }
        )
        if not reads:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="agent skipped fs_read; repair must use tool output",
            )

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

        # Written content must match repair(fs_read output), not an opaque fixture copy
        read_raw = (reads[0].get("output") or {}).get("content", "")
        try:
            derived = json.loads(repair_broken_config(read_raw))
            derived_match = data == derived
        except (ValueError, json.JSONDecodeError):
            derived_match = False
        checks.append(
            {
                "name": "artifact_derived_from_read",
                "passed": derived_match,
            }
        )
        if not derived_match:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="written config was not derived from fs_read repair",
            )

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
