from __future__ import annotations

import html
from typing import Any

from backend.models.entities import RequirementReview

SECTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("ambiguity_list", "需求歧义", "#165dff"),
    ("miss_logic_list", "逻辑缺失", "#ff7d00"),
    ("untestable_list", "可测性缺陷", "#86909c"),
    ("biz_risk_list", "业务风险", "#f53f3f"),
)


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _render_issue_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p class='empty'>（无）</p>"
    rows = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        rows.append(
            f"<tr>"
            f"<td>{idx}</td>"
            f"<td>{_esc(item.get('pos'))}</td>"
            f"<td><span class='tag'>{_esc(item.get('level'))}</span></td>"
            f"<td>{_esc(item.get('desc'))}</td>"
            f"<td>{_esc(item.get('suggest'))}</td>"
            f"</tr>"
        )
    return (
        "<table><thead><tr><th>#</th><th>位置</th><th>等级</th><th>描述</th><th>建议</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def build_requirement_review_html(review: RequirementReview, *, project_name: str = "") -> str:
    payload = review.result_json if isinstance(review.result_json, dict) else {}
    sections_html = []
    for key, title, color in SECTION_SPECS:
        count = len(payload.get(key) or [])
        sections_html.append(
            f"<section class='block'><h2 style='border-left:4px solid {color}'>{_esc(title)} "
            f"<span class='count'>{count}</span></h2>{_render_issue_table(payload.get(key) or [])}</section>"
        )

    source = ""
    if getattr(review, "source_filename", None):
        source = f"<p>来源文件：<code>{_esc(review.source_filename)}</code>（{_esc(getattr(review, 'source_format', '') or '-')}）</p>"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>需求预评审 #{review.id}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1d2129; }}
header {{ margin-bottom: 20px; }}
.meta {{ color: #4e5969; font-size: 14px; }}
h1 {{ margin: 0 0 8px; font-size: 22px; }}
.block {{ margin: 20px 0; }}
h2 {{ font-size: 16px; padding-left: 8px; }}
.count {{ background: #f2f3f5; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border: 1px solid #e5e6eb; padding: 8px; vertical-align: top; }}
th {{ background: #f7f8fa; text-align: left; }}
.tag {{ display: inline-block; padding: 2px 6px; border-radius: 4px; background: #e8f3ff; }}
.snapshot {{ background: #fafafa; padding: 12px; border-radius: 6px; white-space: pre-wrap; font-size: 12px; max-height: 320px; overflow: auto; }}
.empty {{ color: #86909c; }}
</style></head><body>
<header>
  <h1>AI 需求预评审报告</h1>
  <div class="meta">
    <p>项目：{_esc(project_name or review.project_id)} · 评审 #{review.id} · 模型 {_esc(review.model_name)}</p>
    <p>时间：{_esc(review.created_at)}</p>
    {source}
  </div>
</header>
<h2>需求原文快照</h2>
<div class="snapshot">{_esc(review.requirement_text[:12000])}</div>
{''.join(sections_html)}
</body></html>"""
