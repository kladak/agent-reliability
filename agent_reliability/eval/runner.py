"""Offline eval runner: execute tasks, grade, write JSON report."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_reliability.observe.trace import TraceSink
from agent_reliability.runtime.mock_agent import MockAgentRuntime
from agent_reliability.runtime.state_store import StateStore
from agent_reliability.tasks import TASK_REGISTRY, get_task
from agent_reliability.tasks.base import TaskContext
from agent_reliability.tools.filesystem import FsReadTool, FsWriteTool
from agent_reliability.tools.flaky_echo import FlakyEchoTool
from agent_reliability.tools.router import ToolRouter


def _default_report_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path("reports")
    out.mkdir(parents=True, exist_ok=True)
    return out / f"eval-offline-{stamp}.json"


def run_offline(
    *,
    task_ids: list[str] | None = None,
    report_path: Path | None = None,
    traces_dir: Path | None = None,
) -> dict[str, Any]:
    selected = task_ids or sorted(TASK_REGISTRY.keys())
    report_path = report_path or _default_report_path()
    traces_dir = traces_dir or Path("traces")
    traces_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    started = time.perf_counter()

    for task_id in selected:
        task = get_task(task_id)
        config = task.agent_config()
        run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory(prefix=f"{task_id}-") as tmp:
            workspace = Path(tmp)
            ctx = TaskContext(
                workspace=workspace,
                fixtures_dir=Path("fixtures") / task_id,
                run_id=run_id,
            )
            task.setup(ctx)

            trace_path = traces_dir / f"{task_id}-{run_id}.jsonl"
            with TraceSink(trace_path) as sink:
                tools = [
                    FsReadTool(workspace),
                    FsWriteTool(workspace),
                    FlakyEchoTool(max_retries=5),
                    *task.extra_tools(ctx),
                ]
                router = ToolRouter(tools, trace=sink, run_id=run_id)
                agent = MockAgentRuntime(
                    router,
                    trace=sink,
                    config=config,
                    state_store=StateStore(workspace / "state"),
                    policy=task.policy(),
                )
                plan = task.build_plan(ctx)
                outcome = task.execute(
                    ctx, agent=agent, plan=plan, trace_path=trace_path
                )
                grade = task.grade(ctx, outcome)

            results.append(
                {
                    "task_id": task_id,
                    "run_id": run_id,
                    "passed": grade.passed,
                    # Top-level failure_class is for failed grades only; runtime class kept separately
                    # (e.g. T5 correctly refuses with policy_violation but grade passes).
                    "failure_class": (
                        None
                        if grade.passed
                        else (grade.failure_class or outcome.failure_class)
                    ),
                    "outcome_failure_class": outcome.failure_class,
                    "grade_message": grade.message,
                    "checks": grade.checks,
                    "latency_ms": outcome.latency_ms,
                    "tokens_in": outcome.tokens_in,
                    "tokens_out": outcome.tokens_out,
                    "cost_usd": outcome.cost_usd,
                    "steps_completed": outcome.steps_completed,
                    "trace_path": str(trace_path),
                    "model": config.model,
                    "config": config.model_dump(),
                }
            )

    elapsed_ms = (time.perf_counter() - started) * 1000
    passed = sum(1 for r in results if r["passed"])
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline",
        "task_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": (passed / len(results)) if results else 0.0,
        "total_latency_ms": elapsed_ms,
        "results": results,
        # Only the metrics measured above; nothing is derived or estimated.
        "notes": (
            "Deterministic mock-agent eval; cost_usd/tokens come from "
            "MockAgentConfig counters, not a live bill."
        ),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent reliability eval runner")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run mock-agent offline eval (no paid LLM)",
    )
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=None,
        help="Optional task ids (default: all registered)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Output JSON report path",
    )
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=Path("traces"),
        help="Directory for JSONL traces",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE", "CANDIDATE"),
        help="Compare two existing report JSON files and exit",
    )
    args = parser.parse_args(argv)

    if args.compare:
        from agent_reliability.eval.compare import compare_reports, load_report

        baseline = load_report(Path(args.compare[0]))
        candidate = load_report(Path(args.compare[1]))
        diff = compare_reports(baseline, candidate)
        print(json.dumps(diff, indent=2))
        # Non-zero if regressions detected
        return 1 if diff.get("regressions") else 0

    if not args.offline:
        parser.error("v0 runner requires --offline (live LLM path not implemented yet)")

    report = run_offline(
        task_ids=args.tasks,
        report_path=args.report,
        traces_dir=args.traces_dir,
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "failed": report["failed"],
                "task_count": report["task_count"],
                "report": str(args.report or "reports/"),
            },
            indent=2,
        )
    )
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
