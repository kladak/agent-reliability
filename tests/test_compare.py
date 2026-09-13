from agent_reliability.eval.compare import compare_reports


def test_compare_detects_regression() -> None:
    baseline = {
        "passed": 2,
        "failed": 0,
        "results": [
            {"task_id": "T1_file_repair", "passed": True, "failure_class": None, "latency_ms": 1, "tokens_in": 10, "tokens_out": 5},
            {"task_id": "T3_flaky_tool", "passed": True, "failure_class": None, "latency_ms": 2, "tokens_in": 20, "tokens_out": 10},
        ],
    }
    candidate = {
        "passed": 1,
        "failed": 1,
        "results": [
            {"task_id": "T1_file_repair", "passed": True, "failure_class": None, "latency_ms": 1.5, "tokens_in": 10, "tokens_out": 5},
            {"task_id": "T3_flaky_tool", "passed": False, "failure_class": "retry_exhausted", "latency_ms": 9, "tokens_in": 20, "tokens_out": 10},
        ],
    }
    diff = compare_reports(baseline, candidate)
    assert "T3_flaky_tool" in diff["regressions"]
    by_id = {r["task_id"]: r for r in diff["per_task"]}
    assert by_id["T3_flaky_tool"]["status"] == "regressed"
