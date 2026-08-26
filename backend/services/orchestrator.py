from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import ExecutionJob, ItemStatus, Project, RunStatus, TestRun, TestRunItem
from backend.services.api_run_service import execute_project_api_dsl, should_use_dsl_api
from backend.services.audit_service import log_action
from backend.models.entities import FunctionalCase
from backend.services.engines.ui_playwright import execute_ui_agent
from backend.services.plan_run_service import execute_functional_cases
from backend.services.perf_run_service import execute_project_perf_k6, should_use_k6_perf
from backend.services.repo_workspace import resolve_project_code_root
from backend.services.security_run_service import execute_integrated_security, should_integrate_ai_security

ALLOWED_KINDS = (
    "unit",
    "functional",
    "api",
    "perf_backend",
    "perf_frontend",
    "sec_backend",
    "sec_frontend",
    "ui",
)

DEFAULT_COMMANDS = {
    "unit": "pytest -q",
    "functional": "functional://suite",
    "api": "pytest -q tests/api",
    "perf_backend": "k6 run perf/backend.js",
    "perf_frontend": "k6 run perf/frontend.js",
    "sec_backend": "bandit -r . -q",
    "sec_frontend": "npm audit --audit-level=high",
    "ui": "playwright test",
}

# pytest: 5 = no tests collected; 4 = usage error (often missing path).
_PYTEST_NO_TESTS = 5
_PYTEST_USAGE_ERROR = 4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_run_cancel_requested(db: Session, run_id: int) -> bool:
    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one_or_none()
    return bool(job and job.cancel_requested)


def resolve_run_status(item_statuses: list[str]) -> str:
    """Run is failed if any item failed or errored; otherwise completed."""
    if any(s in {ItemStatus.failed.value, ItemStatus.error.value} for s in item_statuses):
        return RunStatus.failed.value
    return RunStatus.completed.value


def classify_shell_result(
    *,
    kind: str,
    command: str,
    returncode: int | None,
    stdout: str,
    stderr: str,
    cwd: str | Path,
) -> tuple[str, dict]:
    """Map shell exit to item status. Missing tooling/paths/tests → skipped, not failed."""
    out = stdout or ""
    err = stderr or ""
    combined = f"{out}\n{err}".lower()
    code = returncode if returncode is not None else -1

    if code == 127 or "command not found" in combined:
        return ItemStatus.skipped.value, {"reason": "测试工具未安装或不在 PATH"}

    # pytest path missing (e.g. tests/api) or usage error with no collectable suite
    if "file or directory not found" in combined or "no such file or directory" in combined:
        return ItemStatus.skipped.value, {
            "reason": f"测试路径不存在，已跳过（command: {command}）",
            "exit_code": code,
        }

    if kind in {"unit", "api"} or "pytest" in command:
        if code == _PYTEST_NO_TESTS or "no tests ran" in combined or "collected 0 item" in combined:
            return ItemStatus.skipped.value, {
                "reason": f"未收集到可执行测试（code_root={cwd}）",
                "exit_code": code,
            }
        if code == _PYTEST_USAGE_ERROR:
            return ItemStatus.skipped.value, {
                "reason": f"pytest 用法/路径错误，已跳过（command: {command}）",
                "exit_code": code,
            }

    # k6 / bandit style missing script
    if kind.startswith("perf_") and code != 0 and (
        "could not find file" in combined or "no such file" in combined or "stat " in combined
    ):
        return ItemStatus.skipped.value, {
            "reason": f"压测脚本不存在，已跳过（command: {command}）",
            "exit_code": code,
        }

    if code == 0:
        return ItemStatus.passed.value, {}
    return ItemStatus.failed.value, {"exit_code": code}


def create_run_with_items(db: Session, project_id: int, kinds: list[str]) -> TestRun:
    chosen = [k for k in kinds if k in ALLOWED_KINDS] or list(ALLOWED_KINDS)
    run = TestRun(project_id=project_id, status=RunStatus.pending.value)
    db.add(run)
    db.commit()
    db.refresh(run)
    for kind in chosen:
        db.add(TestRunItem(run_id=run.id, kind=kind, status=ItemStatus.pending.value))
    db.commit()
    db.refresh(run)
    return run


def execute_run(
    db: Session,
    run: TestRun,
    project: Project,
    overrides: dict[str, str] | None,
    run_options: dict | None = None,
    job_id: int | None = None,
) -> None:
    settings = get_settings()
    run.status = RunStatus.running.value
    run.error_message = None
    db.commit()

    try:
        cwd = resolve_project_code_root(project)
    except Exception as e:  # noqa: BLE001
        for item in sorted(run.items, key=lambda x: x.id):
            item.command = None
            item.status = ItemStatus.skipped.value
            item.detail = {"reason": str(e)}
            item.started_at = _now()
            item.finished_at = _now()
        run.status = RunStatus.completed.value
        run.completed_at = _now()
        db.commit()
        log_action(
            db,
            module="runs",
            action="run.sync_repo_failed",
            level="warning",
            message=f"run #{run.id} skipped because repository could not be prepared",
            detail={"run_id": run.id, "project_id": project.id, "reason": str(e)},
        )
        return

    try:
        for item in sorted(run.items, key=lambda x: x.id):
            if is_run_cancel_requested(db, run.id):
                item.status = ItemStatus.skipped.value
                item.detail = {"reason": "run cancelled by user"}
                item.finished_at = _now()
                db.commit()
                run.status = RunStatus.cancelled.value
                run.completed_at = _now()
                db.commit()
                log_action(
                    db,
                    module="runs",
                    action="run.cancelled",
                    message=f"run #{run.id} cancelled",
                    detail={"run_id": run.id, "job_id": job_id},
                )
                return

            cmd = (overrides or {}).get(item.kind) or DEFAULT_COMMANDS[item.kind]
            item.command = cmd
            item.status = ItemStatus.running.value
            item.started_at = _now()
            db.commit()

            if item.kind == "functional":
                case_ids = (run_options or {}).get("functional_case_ids") or []
                if not case_ids:
                    item.status = ItemStatus.skipped.value
                    item.detail = {"reason": "未指定 suite/plan 或 functional_case_ids 为空"}
                    item.finished_at = _now()
                    db.commit()
                    continue
                fn_result = execute_functional_cases(db, project_id=project.id, case_ids=case_ids)
                item.command = fn_result.get("command_label") or "functional://suite"
                item.exit_code = fn_result.get("exit_code")
                item.stdout = fn_result.get("stdout")
                item.stderr = fn_result.get("stderr")
                item.detail = fn_result.get("detail")
                st = fn_result.get("status")
                item.status = (
                    ItemStatus.skipped.value
                    if st == "skipped"
                    else ItemStatus.passed.value
                    if st == "passed"
                    else ItemStatus.failed.value
                )
                item.finished_at = _now()
                db.commit()
                continue

            if item.kind == "ui":
                ui_script = (run_options or {}).get("ui_script")
                if not ui_script:
                    bound = (
                        db.query(FunctionalCase)
                        .filter(
                            FunctionalCase.project_id == project.id,
                            FunctionalCase.ui_script.isnot(None),
                        )
                        .order_by(FunctionalCase.id.asc())
                        .first()
                    )
                    if bound:
                        ui_script = bound.ui_script
                if ui_script:
                    ui_result = execute_ui_agent(
                        ui_script,
                        base_url=str((run_options or {}).get("ui_base_url") or "http://127.0.0.1:5173"),
                        embed_screenshots=False,
                    )
                    item.command = "playwright://gui-agent"
                    item.exit_code = 0 if ui_result.get("status") == "passed" else 1
                    item.stdout = ui_result.get("stdout")
                    item.stderr = ui_result.get("stderr")
                    traces = ui_result.get("traces") if isinstance(ui_result.get("traces"), list) else []
                    slim_traces = [
                        {k: v for k, v in row.items() if k != "screenshot_data_url"}
                        if isinstance(row, dict)
                        else row
                        for row in traces
                    ]
                    item.detail = {
                        **(ui_result.get("detail") if isinstance(ui_result.get("detail"), dict) else {}),
                        "traces": slim_traces,
                    }
                    st = ui_result.get("status")
                    item.status = (
                        ItemStatus.skipped.value
                        if st == "skipped"
                        else ItemStatus.passed.value
                        if st == "passed"
                        else ItemStatus.failed.value
                    )
                    item.finished_at = _now()
                    db.commit()
                    continue

            if item.kind == "api" and should_use_dsl_api(db, project.id, run_options):
                dsl_result = execute_project_api_dsl(db, project.id, run_options)
                item.command = dsl_result.get("command_label") or "dsl://api-automation"
                item.exit_code = dsl_result.get("exit_code")
                item.stdout = dsl_result.get("stdout")
                item.stderr = dsl_result.get("stderr")
                item.detail = dsl_result.get("detail")
                st = dsl_result.get("status")
                if st == "skipped":
                    item.status = ItemStatus.skipped.value
                    item.detail = {**(item.detail or {}), "reason": dsl_result.get("detail", {}).get("reason", "")}
                elif st == "passed":
                    item.status = ItemStatus.passed.value
                else:
                    item.status = ItemStatus.failed.value
                item.finished_at = _now()
                db.commit()
                continue

            if item.kind in {"perf_backend", "perf_frontend"} and should_use_k6_perf(db, project.id, run_options):
                perf_result = execute_project_perf_k6(db, project.id, run_options)
                item.command = perf_result.get("command_label") or "k6://perf-plan"
                item.exit_code = perf_result.get("exit_code")
                item.stdout = perf_result.get("stdout")
                item.stderr = perf_result.get("stderr")
                item.detail = perf_result.get("detail")
                st = perf_result.get("status")
                item.status = (
                    ItemStatus.skipped.value
                    if st == "skipped"
                    else ItemStatus.passed.value
                    if st == "passed"
                    else ItemStatus.failed.value
                )
                item.finished_at = _now()
                db.commit()
                continue

            if item.kind in {"sec_backend", "sec_frontend"} and should_integrate_ai_security(
                db, project.id, run_options
            ):
                sec_result = execute_integrated_security(
                    db,
                    project.id,
                    kind=item.kind,
                    run_id=run.id,
                    run_options=run_options,
                    legacy_cmd=cmd,
                    cwd=str(cwd),
                )
                item.command = sec_result.get("command_label") or f"security://{item.kind}"
                item.exit_code = sec_result.get("exit_code")
                item.stdout = sec_result.get("stdout")
                item.stderr = sec_result.get("stderr")
                item.detail = sec_result.get("detail")
                st = sec_result.get("status")
                item.status = (
                    ItemStatus.skipped.value
                    if st == "skipped"
                    else ItemStatus.passed.value
                    if st == "passed"
                    else ItemStatus.failed.value
                )
                item.finished_at = _now()
                db.commit()
                continue

            if not Path(cwd).is_dir():
                item.status = ItemStatus.skipped.value
                item.detail = {"reason": f"code_root 不存在: {cwd}"}
                item.finished_at = _now()
                db.commit()
                continue

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(cwd),
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=settings.default_test_timeout_sec,
                )
                item.exit_code = proc.returncode
                item.stdout = (proc.stdout or "")[-8000:]
                item.stderr = (proc.stderr or "")[-8000:]
                status, detail = classify_shell_result(
                    kind=item.kind,
                    command=cmd,
                    returncode=proc.returncode,
                    stdout=item.stdout or "",
                    stderr=item.stderr or "",
                    cwd=cwd,
                )
                item.status = status
                item.detail = detail
            except subprocess.TimeoutExpired:
                item.status = ItemStatus.error.value
                item.detail = {"reason": "执行超时"}
            except Exception as e:  # noqa: BLE001
                item.status = ItemStatus.error.value
                item.detail = {"reason": str(e)}

            item.finished_at = _now()
            db.commit()

        item_statuses = [item.status for item in run.items]
        run.status = resolve_run_status(item_statuses)
        run.completed_at = _now()
        db.commit()
        log_action(
            db,
            module="runs",
            action="run.completed" if run.status == RunStatus.completed.value else "run.failed",
            message=f"run #{run.id} {run.status}",
            detail={"run_id": run.id, "project_id": project.id, "item_statuses": item_statuses},
            organization_id=project.organization_id,
            project_id=project.id,
        )
        from backend.services.ci_webhook_service import post_pr_comment_if_configured

        post_pr_comment_if_configured(db, run=run, project=project)
    except Exception as e:  # noqa: BLE001
        run.status = RunStatus.failed.value
        run.completed_at = _now()
        run.error_message = str(e)
        db.commit()
        log_action(
            db,
            module="runs",
            action="run.failed",
            level="error",
            message=f"run #{run.id} failed",
            detail={"run_id": run.id, "project_id": project.id, "reason": str(e)},
        )
        raise
