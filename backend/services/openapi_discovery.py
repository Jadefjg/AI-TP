from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml

from backend.models.entities import Project
from backend.services.repo_workspace import is_deployed_url, resolve_project_code_root

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".next",
    "coverage",
    "target",
    ".idea",
    ".vscode",
}

_OPENAPI_NAME_HINTS = ("openapi", "swagger")
_CODE_GLOBS = ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.go", "*.java")

_FASTAPI_DECORATOR = re.compile(
    r"""@(?:app|router|api_router)\.(get|post|put|patch|delete|head|options)\(\s*['"]([^'"]+)['"]""",
    re.I,
)
_EXPRESS_ROUTE = re.compile(
    r"""\.(get|post|put|patch|delete|head|options)\(\s*['"`]([^'"`]+)['"`]""",
    re.I,
)
_GO_GIN = re.compile(
    r"""\.(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\(\s*["']([^"']+)["']""",
)
_JAVA_MAPPING = re.compile(
    r"""@(Get|Post|Put|Patch|Delete)Mapping\(\s*(?:value\s*=\s*)?["']([^"']+)["']""",
    re.I,
)

_DEPLOYED_CANDIDATES = (
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger/v1/swagger.json",
    "/v3/api-docs",
    "/v2/api-docs",
    "/api/openapi.json",
    "/docs/openapi.json",
)


@dataclass
class RouteSignal:
    method: str
    path: str
    source_file: str | None = None


@dataclass
class OpenApiDiscovery:
    source: str
    document: dict[str, Any] | None = None
    signals: list[RouteSignal] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    server_url: str | None = None


def _safe_load_spec(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("{"):
            data = json.loads(raw)
        else:
            data = yaml.safe_load(raw)
    except (json.JSONDecodeError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    if "paths" not in data and "swagger" not in data and "openapi" not in data:
        return None
    return data


def parse_openapi_text(content: str) -> dict[str, Any]:
    doc = _safe_load_spec(content)
    if not doc or not isinstance(doc.get("paths"), dict):
        raise ValueError("OpenAPI/Swagger 内容无效，请提供包含 paths 的 JSON 或 YAML")
    return doc


def fetch_openapi_from_url(url: str) -> tuple[dict[str, Any], str]:
    target = (url or "").strip()
    if not re.match(r"^https?://", target, re.I):
        raise ValueError("请填写以 http:// 或 https:// 开头的 OpenAPI URL")
    candidates = [target]
    # If user pastes a service root, also try common docs endpoints.
    if not any(token in target.lower() for token in ("openapi", "swagger", "api-docs")):
        root = target.rstrip("/") + "/"
        candidates.extend(urljoin(root, suffix.lstrip("/")) for suffix in _DEPLOYED_CANDIDATES)
    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        errors: list[str] = []
        for candidate in candidates:
            try:
                resp = client.get(candidate)
            except httpx.HTTPError as exc:
                errors.append(f"{candidate}: {exc}")
                continue
            if resp.status_code >= 400:
                errors.append(f"{candidate}: HTTP {resp.status_code}")
                continue
            doc = _safe_load_spec(resp.text)
            if doc and isinstance(doc.get("paths"), dict):
                return doc, candidate
            errors.append(f"{candidate}: 非有效 OpenAPI")
    raise ValueError("未能从 URL 拉取到 OpenAPI：" + "; ".join(errors[:4]))


def _looks_like_openapi_file(path: Path) -> bool:
    name = path.name.lower()
    return any(token in name for token in _OPENAPI_NAME_HINTS) and path.suffix.lower() in {
        ".json",
        ".yaml",
        ".yml",
    }


def _iter_project_files(root: Path, *, max_files: int = 800) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def _scan_code_signals(root: Path, *, max_hits: int = 200) -> list[RouteSignal]:
    signals: list[RouteSignal] = []
    seen: set[tuple[str, str]] = set()

    def add(method: str, path: str, source: Path) -> None:
        method_u = method.upper()
        path_n = path if path.startswith("/") else f"/{path}"
        key = (method_u, path_n)
        if key in seen:
            return
        seen.add(key)
        signals.append(RouteSignal(method=method_u, path=path_n, source_file=str(source.relative_to(root))))

    for path in _iter_project_files(root):
        if len(signals) >= max_hits:
            break
        if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java"}:
            continue
        try:
            if path.stat().st_size > 400_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        patterns = (_FASTAPI_DECORATOR, _EXPRESS_ROUTE, _GO_GIN, _JAVA_MAPPING)
        for pattern in patterns:
            for match in pattern.finditer(text):
                add(match.group(1), match.group(2), path)
                if len(signals) >= max_hits:
                    return signals
    return signals


def _find_existing_spec(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    candidates: list[Path] = []
    for path in _iter_project_files(root, max_files=1200):
        if _looks_like_openapi_file(path):
            candidates.append(path)
    preferred = sorted(
        candidates,
        key=lambda p: (
            0 if "openapi" in p.name.lower() else 1,
            0 if p.suffix.lower() == ".json" else 1,
            len(p.parts),
        ),
    )
    for path in preferred[:12]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        doc = _safe_load_spec(text)
        if doc and isinstance(doc.get("paths"), dict):
            return doc, str(path.relative_to(root))
    return None, None


def _fetch_deployed_spec(base_url: str) -> tuple[dict[str, Any] | None, str | None]:
    root = base_url.rstrip("/") + "/"
    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
        for suffix in _DEPLOYED_CANDIDATES:
            url = urljoin(root, suffix.lstrip("/"))
            try:
                resp = client.get(url)
            except httpx.HTTPError:
                continue
            if resp.status_code >= 400:
                continue
            doc = _safe_load_spec(resp.text)
            if doc and isinstance(doc.get("paths"), dict):
                return doc, url
    return None, None


def build_openapi_from_signals(
    *,
    project_name: str,
    signals: list[RouteSignal],
    server_url: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for signal in signals:
        item = paths.setdefault(signal.path, {})
        item[signal.method.lower()] = {
            "summary": f"{signal.method} {signal.path}",
            "operationId": f"{signal.method.lower()}_{re.sub(r'[^a-zA-Z0-9]+', '_', signal.path).strip('_')}",
            "responses": {
                "200": {"description": "Successful response"},
            },
        }
        if signal.source_file:
            item[signal.method.lower()]["description"] = f"Discovered from {signal.source_file}"

    if not paths:
        paths = {
            "/system/health": {
                "get": {
                    "summary": "Health check",
                    "operationId": "get_system_health",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        }

    doc: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": f"{project_name} API",
            "version": "1.0.0",
            "description": description
            or "Auto-generated OpenAPI document from project context",
        },
        "paths": paths,
    }
    if server_url:
        doc["servers"] = [{"url": server_url.rstrip("/")}]
    return doc


def format_signals_for_prompt(signals: list[RouteSignal], *, limit: int = 80) -> str:
    if not signals:
        return "（未从代码中扫描到明确路由，请根据项目描述推断常见 REST 接口）"
    lines = []
    for item in signals[:limit]:
        src = f" · {item.source_file}" if item.source_file else ""
        lines.append(f"- {item.method} {item.path}{src}")
    if len(signals) > limit:
        lines.append(f"... 其余 {len(signals) - limit} 条已省略")
    return "\n".join(lines)


def discover_project_openapi(project: Project) -> OpenApiDiscovery:
    source = (project.repo_source or "local").strip().lower() or "local"
    notes: list[str] = []
    server_url: str | None = None
    signals: list[RouteSignal] = []

    if source == "deployed" or is_deployed_url(project.code_root or ""):
        server_url = (project.code_root or "").strip().rstrip("/")
        notes.append(f"已部署地址: {server_url}")
        doc, fetched_from = _fetch_deployed_spec(server_url)
        if doc:
            notes.append(f"从运行环境拉取 OpenAPI: {fetched_from}")
            return OpenApiDiscovery(
                source="deployed_fetch",
                document=doc,
                signals=[],
                notes=notes,
                server_url=server_url,
            )
        notes.append("部署环境未直接暴露 openapi/swagger 文档端点，将基于项目上下文生成")
        return OpenApiDiscovery(
            source="deployed_missing",
            document=None,
            signals=[],
            notes=notes,
            server_url=server_url,
        )

    try:
        root = resolve_project_code_root(project)
    except RuntimeError as exc:
        notes.append(str(exc))
        return OpenApiDiscovery(source="unavailable", document=None, signals=[], notes=notes)

    if not root.exists() or not root.is_dir():
        notes.append(f"代码目录不可用: {root}")
        return OpenApiDiscovery(source="unavailable", document=None, signals=[], notes=notes)

    notes.append(f"扫描目录: {root}")
    doc, rel = _find_existing_spec(root)
    if doc:
        notes.append(f"在仓库中发现现有文档: {rel}")
        return OpenApiDiscovery(
            source="repo_file",
            document=doc,
            signals=[],
            notes=notes,
            server_url=None,
        )

    signals = _scan_code_signals(root)
    notes.append(f"从源码扫描到路由信号 {len(signals)} 条")
    return OpenApiDiscovery(
        source="code_scan",
        document=None,
        signals=signals,
        notes=notes,
        server_url=None,
    )


def wrap_openapi_artifact_payload(
    document: dict[str, Any],
    *,
    source: str,
    remark: str,
) -> dict[str, Any]:
    return {
        "openapi_document": document,
        "openapi_json": json.dumps(document, ensure_ascii=False, indent=2),
        "source": source,
        "remark": remark,
        "path_count": len(document.get("paths") or {}),
    }
