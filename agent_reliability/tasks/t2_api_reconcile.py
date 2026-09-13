"""T2: fetch inventories via http_get, reconcile from HTTP bodies, write report.

build_plan does not precompute the report from fixture files. The reactive
planner reconciles only after both http_get tool results are in hand. Skipping
HTTP tools cannot produce a correct derived report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.runtime.mock_agent import RunOutcome, ToolPlanStep
from agent_reliability.tasks.base import BaseTask, GradeResult, TaskContext
from agent_reliability.tools.base import BaseTool
from agent_reliability.tools.http_mock import MockHttpTool

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


def _body_from_http_result(result: dict[str, Any]) -> list[dict] | None:
    output = result.get("output") or {}
    body = output.get("body")
    if isinstance(body, list):
        return body
    return None


class T2ApiReconcile(BaseTask):
    task_id = "T2_api_reconcile"
    description = "Call a mock HTTP API, reconcile two lists, write a report"

    def setup(self, ctx: TaskContext) -> None:
        ctx.workspace.mkdir(parents=True, exist_ok=True)

    def extra_tools(self, ctx: TaskContext) -> list[BaseTool]:
        return [MockHttpTool(self.routes())]

    def routes(self) -> dict:
        return {
            "/inventory/a": json.loads((FIXTURES / "inventory_a.json").read_text()),
            "/inventory/b": json.loads((FIXTURES / "inventory_b.json").read_text()),
        }

    def build_plan(self, ctx: TaskContext) -> list[ToolPlanStep]:
        # Skeleton — report content is derived in execute from http_get bodies.
        return [
            ToolPlanStep(tool="http_get", args={"path": "/inventory/a"}),
            ToolPlanStep(tool="http_get", args={"path": "/inventory/b"}),
            ToolPlanStep(
                tool="fs_write",
                args={
                    "path": "reconcile_report.json",
                    "content": "<derived-from-http_get>",
                },
                idempotency_key=f"t2-report-{ctx.run_id}",
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
        write_key = f"t2-report-{ctx.run_id}"

        def planner(results: list[dict[str, Any]]) -> ToolPlanStep | None:
            http_ok = [
                r
                for r in results
                if r.get("tool") == "http_get" and r.get("ok")
            ]
            paths = {
                ((r.get("output") or {}).get("path")) for r in http_ok
            }

            if "/inventory/a" not in paths:
                return ToolPlanStep(tool="http_get", args={"path": "/inventory/a"})
            if "/inventory/b" not in paths:
                return ToolPlanStep(tool="http_get", args={"path": "/inventory/b"})

            writes = [r for r in results if r.get("tool") == "fs_write"]
            if writes:
                return None

            by_path = {
                (r.get("output") or {}).get("path"): r for r in http_ok
            }
            list_a = _body_from_http_result(by_path["/inventory/a"])
            list_b = _body_from_http_result(by_path["/inventory/b"])
            if list_a is None or list_b is None:
                return None
            report = reconcile(list_a, list_b)
            content = json.dumps(report, indent=2) + "\n"
            return ToolPlanStep(
                tool="fs_write",
                args={"path": "reconcile_report.json", "content": content},
                idempotency_key=write_key,
            )

        return agent.run_reactive(planner, run_id=ctx.run_id)

    def grade(self, ctx: TaskContext, outcome: RunOutcome) -> GradeResult:
        checks: list[dict] = []
        expected = json.loads((FIXTURES / "expected_report.json").read_text())
        path = ctx.workspace / "reconcile_report.json"

        http_calls = [r for r in outcome.tool_results if r.get("tool") == "http_get"]
        paths = [
            ((r.get("output") or {}).get("path")) for r in http_calls if r.get("ok")
        ]
        fetched_both = "/inventory/a" in paths and "/inventory/b" in paths
        checks.append(
            {
                "name": "fetched_both_inventories",
                "passed": fetched_both,
                "paths": paths,
            }
        )
        if not fetched_both:
            return GradeResult(
                passed=False,
                failure_class=FailureClass.TASK_ASSERTION_FAILED.value,
                checks=checks,
                message="agent skipped http_get for one or both inventories",
            )

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

        # Require the report equals reconcile(HTTP bodies), not fixture-only math
        by_path = {
            (r.get("output") or {}).get("path"): r
            for r in http_calls
            if r.get("ok")
        }
        list_a = _body_from_http_result(by_path["/inventory/a"])
        list_b = _body_from_http_result(by_path["/inventory/b"])
        derived = reconcile(list_a or [], list_b or [])
        derived_match = got == derived
        checks.append(
            {
                "name": "report_derived_from_http",
                "passed": derived_match,
                "derived": derived,
            }
        )

        if not (match and derived_match and outcome.ok):
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
