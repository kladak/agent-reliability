"""Compare two offline eval reports (baseline vs candidate)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_report(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Diff pass/fail and failure classes only — no invented scores.

    regressions: tasks that passed in baseline but failed in candidate,
    or that gained a new failure_class relative to baseline.
    """
    base_by = {r["task_id"]: r for r in baseline.get("results", [])}
    cand_by = {r["task_id"]: r for r in candidate.get("results", [])}
    task_ids = sorted(set(base_by) | set(cand_by))

    per_task: list[dict[str, Any]] = []
    regressions: list[str] = []

    for tid in task_ids:
        b = base_by.get(tid)
        c = cand_by.get(tid)
        entry: dict[str, Any] = {"task_id": tid}
        if b is None:
            entry["status"] = "added_in_candidate"
            entry["candidate_passed"] = c.get("passed") if c else None
        elif c is None:
            entry["status"] = "missing_in_candidate"
            regressions.append(tid)
        else:
            entry["baseline_passed"] = b.get("passed")
            entry["candidate_passed"] = c.get("passed")
            entry["baseline_failure_class"] = b.get("failure_class")
            entry["candidate_failure_class"] = c.get("failure_class")
            entry["latency_ms_delta"] = (c.get("latency_ms") or 0) - (b.get("latency_ms") or 0)
            entry["tokens_total_delta"] = (
                (c.get("tokens_in") or 0)
                + (c.get("tokens_out") or 0)
                - (b.get("tokens_in") or 0)
                - (b.get("tokens_out") or 0)
            )
            if b.get("passed") and not c.get("passed"):
                entry["status"] = "regressed"
                regressions.append(tid)
            elif b.get("passed") == c.get("passed"):
                entry["status"] = "unchanged"
            elif not b.get("passed") and c.get("passed"):
                entry["status"] = "improved"
            else:
                entry["status"] = "changed"
        per_task.append(entry)

    return {
        "baseline_passed": baseline.get("passed"),
        "candidate_passed": candidate.get("passed"),
        "baseline_failed": baseline.get("failed"),
        "candidate_failed": candidate.get("failed"),
        "regressions": regressions,
        "per_task": per_task,
        "notes": "Comparison uses only measured pass/fail, failure_class, latency, tokens.",
    }
