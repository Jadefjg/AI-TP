from __future__ import annotations

import re
import subprocess
from pathlib import Path

from backend.models.entities import Project

_GIT_SSH_PATTERN = re.compile(r"^(git@|ssh://).+")
_HTTP_PATTERN = re.compile(r"^https?://", re.I)
_GIT_HOST_PATTERN = re.compile(
    r"(github\.com|gitlab\.com|gitee\.com|bitbucket\.org|gitcode\.com)",
    re.I,
)


def is_remote_repo(location: str) -> bool:
    """True when location looks like a Git remote (not a deployed app URL)."""
    value = (location or "").strip()
    if not value:
        return False
    if _GIT_SSH_PATTERN.match(value):
        return True
    if not _HTTP_PATTERN.match(value):
        return False
    lowered = value.lower()
    if lowered.endswith(".git") or "/.git/" in lowered or "/git/" in lowered:
        return True
    return bool(_GIT_HOST_PATTERN.search(value))


def is_deployed_url(location: str) -> bool:
    value = (location or "").strip()
    if not _HTTP_PATTERN.match(value):
        return False
    return not is_remote_repo(value)


def resolve_project_code_root(project: Project) -> Path:
    repo_source = (project.repo_source or "").strip().lower() or "local"
    if repo_source == "deployed":
        raise RuntimeError("已部署项目仅绑定运行地址，不提供本地代码工作区")
    if repo_source == "remote":
        return sync_remote_repo(project)
    # legacy rows may have git URL but still labelled local
    if is_remote_repo(project.code_root):
        return sync_remote_repo(project)
    return Path(project.code_root).expanduser()


def sync_remote_repo(project: Project) -> Path:
    location = (project.code_root or "").strip()
    if not is_remote_repo(location):
        raise RuntimeError("远程仓库地址格式不正确，仅支持 http/https/ssh/git 地址")

    repo_dir = Path("data") / "repos" / f"project-{project.id}"
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    branch = (project.repo_branch or "").strip()
    if not (repo_dir / ".git").exists():
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([location, str(repo_dir)])
        _run_git(cmd, repo_dir.parent)
        return repo_dir

    _run_git(["git", "-C", str(repo_dir), "fetch", "--all", "--prune"], repo_dir.parent)
    if branch:
        _run_git(["git", "-C", str(repo_dir), "checkout", branch], repo_dir.parent)
        _run_git(["git", "-C", str(repo_dir), "pull", "--ff-only", "origin", branch], repo_dir.parent)
    else:
        _run_git(["git", "-C", str(repo_dir), "pull", "--ff-only"], repo_dir.parent)
    return repo_dir


def _run_git(cmd: list[str], cwd: Path) -> None:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git 未安装或不在 PATH 中，无法同步远程仓库") from exc

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "git command failed").strip()
        raise RuntimeError(f"远程仓库同步失败: {msg}")
