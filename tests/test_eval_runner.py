from pathlib import Path

from agent_reliability.eval.runner import run_offline


def test_offline_eval_report(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    traces = tmp_path / "traces"
    report = run_offline(
        task_ids=["T1_file_repair", "T3_flaky_tool"],
        report_path=report_path,
        traces_dir=traces,
    )
    assert report["failed"] == 0
    assert report["passed"] == 2
    assert report_path.exists()
    assert report["mode"] == "offline"
