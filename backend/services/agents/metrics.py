"""Monitoring-layer rollups for specialized Agents (coverage + false-positive rate)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.entities import SecurityScanJob, TestRunItem

KIND_TO_AGENT = {
    "functional": "requirement",
    "ui": "ui",
    "api": "interface",
    "perf_backend": "perf",
    "perf_frontend": "perf",
    "sec_backend": "security",
    "sec_frontend": "security",
}


def agent_quality_stats(db: Session) -> dict:
    coverage: dict[str, dict[str, int]] = {
        key: {"items": 0, "passed": 0, "failed": 0, "skipped": 0}
        for key in ("requirement", "ui", "interface", "perf", "security")
    }
    items = db.query(TestRunItem.kind, TestRunItem.status).all()
    for kind, status in items:
        agent_key = KIND_TO_AGENT.get(str(kind or ""))
        if not agent_key:
            continue
        bucket = coverage[agent_key]
        bucket["items"] += 1
        normalized = str(status or "").lower()
        if normalized in {"passed", "completed", "success"}:
            bucket["passed"] += 1
        elif normalized in {"skipped"}:
            bucket["skipped"] += 1
        elif normalized in {"failed", "error"}:
            bucket["failed"] += 1

    reviewed = 0
    false_positive = 0
    confirmed = 0
    jobs = db.query(SecurityScanJob.finding_reviews).all()
    for (reviews,) in jobs:
        if not isinstance(reviews, dict):
            continue
        for row in reviews.values():
            status = ""
            if isinstance(row, dict):
                status = str(row.get("status") or "")
            elif isinstance(row, str):
                status = row
            if not status:
                continue
            reviewed += 1
            if status == "false_positive":
                false_positive += 1
            elif status == "confirmed":
                confirmed += 1

    rate = round(false_positive / reviewed, 4) if reviewed else 0.0
    return {
        "coverage": coverage,
        "security_false_positive": {
            "reviewed": reviewed,
            "false_positive": false_positive,
            "confirmed": confirmed,
            "rate": rate,
        },
    }
