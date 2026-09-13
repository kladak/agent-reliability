from pathlib import Path

from agent_reliability.eval.runner import run_offline


def test_offline_eval_report_all_tasks(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    traces = tmp_path / "traces"
    report = run_offline(report_path=report_path, traces_dir=traces)
    assert report["task_count"] == 6
    assert report["failed"] == 0, report
    assert report["passed"] == 6
    assert report_path.exists()
    assert report["mode"] == "offline"
