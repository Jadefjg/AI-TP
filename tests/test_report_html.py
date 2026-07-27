"""HTML test report content richness."""

from datetime import datetime, timezone

from backend.models.entities import (
    ItemStatus,
    Organization,
    Project,
    RunStatus,
    TestRun as RunModel,
    TestRunItem as RunItemModel,
)
from backend.services.report_service import build_html_report


def test_build_html_report_includes_reason_and_stdout(db):
    org = Organization(slug="report-demo", name="Report Org", max_projects=10, monthly_ai_token_quota=0)
    db.add(org)
    db.flush()

    project = Project(organization_id=org.id, name="Report Demo", code_root="/tmp/report-demo")
    db.add(project)
    db.flush()

    now = datetime.now(timezone.utc)
    run = RunModel(
        project_id=project.id,
        status=RunStatus.completed.value,
        created_at=now,
        completed_at=now,
    )
    db.add(run)
    db.flush()

    db.add(
        RunItemModel(
            run_id=run.id,
            kind="api",
            status=ItemStatus.skipped.value,
            command="pytest -q tests/api",
            exit_code=None,
            stdout="",
            stderr="",
            detail={"reason": "测试工具未安装或不在 PATH"},
            started_at=now,
            finished_at=now,
        )
    )
    db.add(
        RunItemModel(
            run_id=run.id,
            kind="unit",
            status=ItemStatus.passed.value,
            command="pytest -q",
            exit_code=0,
            stdout="1 passed in 0.12s",
            stderr="",
            detail={"engine": "pytest"},
            started_at=now,
            finished_at=now,
        )
    )
    db.commit()

    report = build_html_report(db, run_id=run.id)
    html = report.content

    assert "测试报告" in html
    assert "Report Demo" in html
    assert "测试工具未安装或不在 PATH" in html
    assert "原因 / 说明" in html
    assert "1 passed in 0.12s" in html
    assert "（无输出）" in html
    assert "执行上下文" in html
    assert html.count("stdout") >= 2
    assert "skipped" in html
    assert "passed" in html
