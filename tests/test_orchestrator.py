from pathlib import Path

from backend.models.entities import ItemStatus, RunStatus
from backend.services.orchestrator import classify_shell_result, resolve_run_status


def test_resolve_run_status_all_passed():
    assert resolve_run_status([ItemStatus.passed.value, ItemStatus.skipped.value]) == RunStatus.completed.value


def test_resolve_run_status_failed_item():
    assert resolve_run_status([ItemStatus.passed.value, ItemStatus.failed.value]) == RunStatus.failed.value


def test_resolve_run_status_error_item():
    assert resolve_run_status([ItemStatus.error.value]) == RunStatus.failed.value


def test_classify_shell_pytest_no_tests_collected():
    status, detail = classify_shell_result(
        kind="unit",
        command="pytest -q",
        returncode=5,
        stdout="\nno tests ran in 0.02s\n",
        stderr="",
        cwd="/tmp/empty-project",
    )
    assert status == ItemStatus.skipped.value
    assert "未收集到" in detail["reason"]


def test_classify_shell_pytest_missing_api_path():
    status, detail = classify_shell_result(
        kind="api",
        command="pytest -q tests/api",
        returncode=4,
        stdout="",
        stderr="ERROR: file or directory not found: tests/api\n",
        cwd="/tmp/empty-project",
    )
    assert status == ItemStatus.skipped.value
    assert "不存在" in detail["reason"]


def test_classify_shell_real_failure_still_failed():
    status, detail = classify_shell_result(
        kind="unit",
        command="pytest -q",
        returncode=1,
        stdout="F\n1 failed",
        stderr="",
        cwd=Path("/tmp/proj"),
    )
    assert status == ItemStatus.failed.value
    assert detail.get("exit_code") == 1


def test_classify_shell_command_not_found():
    status, detail = classify_shell_result(
        kind="perf_backend",
        command="k6 run perf/backend.js",
        returncode=127,
        stdout="",
        stderr="k6: command not found",
        cwd="/tmp/proj",
    )
    assert status == ItemStatus.skipped.value
    assert "未安装" in detail["reason"]
