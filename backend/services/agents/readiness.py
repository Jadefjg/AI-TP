"""Runtime readiness checks for the five pipeline Agents."""
from __future__ import annotations

import shutil
from typing import Any


def _playwright_ready() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False, "未安装 Playwright；执行请使用 worker-tools 镜像或 pip install playwright && playwright install chromium"
    return True, "Playwright 已安装（执行时仍需 Chromium；缺失会 skipped）"


def _k6_ready() -> tuple[bool, str]:
    if shutil.which("k6"):
        return True, "k6 在 PATH 中"
    return False, "未安装 k6；压测执行将 skipped（可使用 worker-tools 镜像）"


def _nuclei_ready() -> tuple[bool, str]:
    if shutil.which("nuclei"):
        return True, "nuclei 在 PATH 中"
    return False, "未安装 nuclei；将回退内置 HTTP 扫描（可选增强）"


def llm_status_payload() -> dict[str, Any]:
    from backend.core.config import get_settings

    settings = get_settings()
    return {
        "configured": settings.llm_configured(),
        "provider": settings.resolved_llm_provider(),
        "high_precision_model": settings.resolved_high_precision_model(),
        "bulk_model": settings.resolved_bulk_model(),
        "stub_on_failure": bool(getattr(settings, "ai_stub_on_failure", True)),
    }


def agent_tool_readiness() -> dict[str, dict[str, Any]]:
    pw_ok, pw_msg = _playwright_ready()
    k6_ok, k6_msg = _k6_ready()
    nuclei_ok, nuclei_msg = _nuclei_ready()
    return {
        "requirement": {
            "generate_ready": True,
            "execute_ready": True,
            "tools": {"llm": "required"},
            "hint": "生成依赖 LLM；无 Key 时使用本地/ stub 分析",
        },
        "ui": {
            "generate_ready": True,
            "execute_ready": pw_ok,
            "tools": {"playwright": {"ready": pw_ok, "detail": pw_msg}},
            "hint": pw_msg,
        },
        "interface": {
            "generate_ready": True,
            "execute_ready": True,
            "tools": {"http": {"ready": True, "detail": "内置 HTTP DSL runner"}},
            "hint": "接口执行无需外部工具",
        },
        "perf": {
            "generate_ready": True,
            "execute_ready": k6_ok,
            "tools": {"k6": {"ready": k6_ok, "detail": k6_msg}},
            "hint": k6_msg,
        },
        "security": {
            "generate_ready": True,
            "execute_ready": True,
            "tools": {
                "builtin": {"ready": True, "detail": "内置 HTTP 启发式扫描"},
                "nuclei": {"ready": nuclei_ok, "detail": nuclei_msg},
            },
            "hint": "内置扫描始终可用；nuclei 为增强项",
        },
    }


def pipeline_status_payload() -> dict[str, Any]:
    from backend.services.agents import list_agent_manifests

    llm = llm_status_payload()
    tools = agent_tool_readiness()
    agents = []
    for index, item in enumerate(list_agent_manifests(), start=1):
        ready = tools.get(item.key, {})
        agents.append(
            {
                "order": index,
                "key": item.key,
                "label": item.label,
                "module_type": item.module_type,
                "engine": item.engine,
                "generate": item.generate,
                "execute": item.execute,
                "layer": item.layer,
                "generate_ready": bool(ready.get("generate_ready", True)),
                "execute_ready": bool(ready.get("execute_ready", True)),
                "tools": ready.get("tools") or {},
                "hint": ready.get("hint") or "",
            }
        )
    return {"llm": llm, "agents": agents}
