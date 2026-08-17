"""Project helpers for SUT / API base URL defaults."""

from __future__ import annotations

from backend.core.defaults import DEFAULT_BASE_URL
from backend.models.entities import Project


def normalize_base_url(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return text.rstrip("/")


def resolve_project_base_url(project: Project) -> str:
    """Prefer persisted project.base_url; else deployed code_root; else platform default."""
    stored = normalize_base_url(project.base_url)
    if stored:
        return stored
    root = (project.code_root or "").strip()
    if project.repo_source == "deployed" and root.lower().startswith(("http://", "https://")):
        return root.rstrip("/")
    return DEFAULT_BASE_URL
