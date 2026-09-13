"""T2: call mock HTTP APIs, reconcile two lists, write a report."""

from __future__ import annotations

import json
from pathlib import Path

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.runtime.mock_agent import RunOutcome, ToolPlanStep
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "T2_api_reconcile"


def reconcile(list_a: list[dict], list_b: list[dict]) -> dict:
    by_a = {row["id"]: row for row in list_a}
    by_b = {row["id"]: row for row in list_b}
    only_a = sorted(set(by_a) - set(by_b))
    only_b = sorted(set(by_b) - set(by_a))
    matched: list[str] = []
    mismatches: list[dict] = []
    for sku in sorted(set(by_a) & set(by_b)):
        if by_a[sku]["qty"] == by_b[sku]["qty"]:
            matched.append(sku)
        else:
            mismatches.append(
                {"id": sku, "qty_a": by_a[sku]["qty"], "qty_b": by_b[sku]["qty"]}
            )
    return {
        "only_in_a": only_a,
        "only_in_b": only_b,
        "qty_mismatch": mismatches,
        "matched": matched,
    }


class T2ApiReconcile(BaseTask):
    task_id = "T2_api_reconcile"
    description = "Call a mock HTTP API, reconcile two lists, write a report"

    def setup(self, ctx: TaskContext) -> None:
        ctx.workspace.mkdir(parents=True, exist_ok=True)

    def routes(self) -> dict:
        return {
            "/inventory/a": json.loads((FIXTURES / "inventory_a.json").read_text()),
            "/inventory/b": json.loads((FIXTURES / "inventory_b.json").read_text()),
        }

    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        list_a = json.loads((FIXTURES / "inventory_a.json").read_text())
        list_b = json.loads((FIXTURES / "inventory_b.json").read_text())
        report = reconcile(list_a, list_b)
        content = json.dumps(report, indent=2) + "\n"
        return [
            ToolPlanStep(tool="http_get", args={"path": "/inventory/a"}),
            ToolPlanStep(tool="http_get", args={"path": "/inventory/b"}),
            ToolPlanStep(
                tool="fs_write",
                args={"path": "reconcile_report.json", "content": content},
                idempotency_key=f"t2-report-{ctx.run_id}",
            ),
        ]

    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        checks: list[dict] = []
        expected = json.loads((FIXTURES / "expected_report.json").read_text())
        path = ctx.workspace / "reconcile_report.json"

        exists = path.exists()
        checks.append({"name": "report_exists", "passed": exists})
        if not exists:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="reconcile_report.json missing",
            )

        got = json.loads(path.read_text(encoding="utf-8"))
        match = got == expected
        checks.append({"name": "report_matches_expected", "passed": match, "got": got})

        http_calls = [r for r in outcome.tool_results if r.get("tool") == "http_get"]
        paths = [((r.get("output") or {}).get("path")) for r in http_calls if r.get("ok")]
        fetched_both = "/inventory/a" in paths and "/inventory/b" in paths
        checks.append(
            {
                "name": "fetched_both_inventories",
                "passed": fetched_both,
                "paths": paths,
            }
        )

        if not (match and fetched_both and outcome.ok):
            return GradeResult(
                passed=False,
                failure_class=(
                    outcome.failure_class
                    if not outcome.ok
                    else FailureClass.TASK_ASSERTION_FAILED.value
                ),
                checks=checks,
                message="T2 assertions failed",
            )
        return GradeResult(passed=True, checks=checks, message="T2 passed")
