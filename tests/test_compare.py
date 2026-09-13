from agent_reliability.eval.compare import compare_reports


def test_compare_detects_regression() -> None:
    baseline = {
        "passed": 2,
        "failed": 0,
        "results": [
            {"task_id": "T1_file_repair", "passed": True, "failure_class": None, "outcome_failure_class": None, "latency_ms": 1, "tokens_in": 10, "tokens_out": 5},
            {"task_id": "T3_flaky_tool", "passed": True, "failure_class": None, "outcome_failure_class": None, "latency_ms": 2, "tokens_in": 20, "tokens_out": 10},
        ],
    }
    candidate = {
        "passed": 1,
        "failed": 1,
        "results": [
            {"task_id": "T1_file_repair", "passed": True, "failure_class": None, "outcome_failure_class": None, "latency_ms": 1.5, "tokens_in": 10, "tokens_out": 5},
            {"task_id": "T3_flaky_tool", "passed": False, "failure_class": "retry_exhausted", "outcome_failure_class": "retry_exhausted", "latency_ms": 9, "tokens_in": 20, "tokens_out": 10},
        ],
    }
    diff = compare_reports(baseline, candidate)
    assert "T3_flaky_tool" in diff["regressions"]
    by_id = {r["task_id"]: r for r in diff["per_task"]}
    assert by_id["T3_flaky_tool"]["status"] == "regressed"


def test_compare_detects_new_failure_class_on_passing_task() -> None:
    """T5-style: grade still passes but outcome_failure_class drifts."""
    baseline = {
        "passed": 1,
        "failed": 0,
        "results": [
            {
                "task_id": "T5_policy_refusal",
                "passed": True,
                "failure_class": None,
                "outcome_failure_class": "policy_violation",
                "latency_ms": 1,
                "tokens_in": 50,
                "tokens_out": 25,
            },
        ],
    }
    candidate = {
        "passed": 1,
        "failed": 0,
        "results": [
            {
                "task_id": "T5_policy_refusal",
                "passed": True,
                "failure_class": None,
                "outcome_failure_class": "tool_execution_error",
                "latency_ms": 1,
                "tokens_in": 50,
                "tokens_out": 25,
            },
        ],
    }
    diff = compare_reports(baseline, candidate)
    assert "T5_policy_refusal" in diff["regressions"]
    by_id = {r["task_id"]: r for r in diff["per_task"]}
    assert by_id["T5_policy_refusal"]["status"] == "failure_class_changed"
    assert by_id["T5_policy_refusal"]["outcome_failure_class_changed"] is True


def test_compare_detects_failure_class_change_on_failed_task() -> None:
    baseline = {
        "passed": 0,
        "failed": 1,
        "results": [
            {
                "task_id": "T3_flaky_tool",
                "passed": False,
                "failure_class": "timeout",
                "outcome_failure_class": "timeout",
                "latency_ms": 1,
                "tokens_in": 0,
                "tokens_out": 0,
            },
        ],
    }
    candidate = {
        "passed": 0,
        "failed": 1,
        "results": [
            {
                "task_id": "T3_flaky_tool",
                "passed": False,
                "failure_class": "retry_exhausted",
                "outcome_failure_class": "retry_exhausted",
                "latency_ms": 1,
                "tokens_in": 0,
                "tokens_out": 0,
            },
        ],
    }
    diff = compare_reports(baseline, candidate)
    assert "T3_flaky_tool" in diff["regressions"]
