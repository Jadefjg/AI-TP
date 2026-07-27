from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from backend.models.entities import RequirementReview

_SECTION_TITLES = (
    ("ambiguity_list", "需求歧义"),
    ("miss_logic_list", "逻辑缺失"),
    ("untestable_list", "可测性缺陷"),
    ("biz_risk_list", "业务风险"),
)

_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
)

_SNAPSHOT_LIMIT = 1800


def _pick_unicode_font() -> tuple[str, str | None]:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return "ReviewSans", str(path)
    return "Helvetica", None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")


def _normalize_items(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    items: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "pos": _text(item.get("pos") or item.get("location") or item.get("position") or "—"),
                "level": _text(item.get("level") or item.get("severity") or "—"),
                "desc": _text(item.get("desc") or item.get("description") or item.get("issue") or ""),
                "suggest": _text(item.get("suggest") or item.get("suggestion") or item.get("advice") or ""),
            }
        )
    return items


class _ReviewPDF(FPDF):
    def __init__(self, *, font_family: str, font_path: str | None) -> None:
        super().__init__()
        self._font_family = font_family
        if font_path:
            self.add_font(font_family, "", font_path)
            self.add_font(font_family, "B", font_path)

    def set_body_font(self, size: float, *, bold: bool = False) -> None:
        self.set_font(self._font_family, "B" if bold else "", size)

    def write_line(self, text: str, *, height: float = 6) -> None:
        self.set_x(self.l_margin)
        self.multi_cell(
            0,
            height,
            text or " ",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )


def _render_issue_section(pdf: _ReviewPDF, title: str, items: list[dict[str, str]]) -> None:
    pdf.set_body_font(13, bold=True)
    pdf.write_line(f"{title}（{len(items)}）", height=8)
    pdf.set_body_font(10)
    if not items:
        pdf.write_line("未发现问题。")
        pdf.ln(2)
        return
    for idx, item in enumerate(items, start=1):
        pdf.set_body_font(10, bold=True)
        pdf.write_line(f"{idx}. [{item['level']}] 位置：{item['pos']}", height=5)
        pdf.set_body_font(10)
        pdf.write_line(f"问题：{item['desc'] or '—'}", height=5)
        pdf.write_line(f"建议：{item['suggest'] or '—'}", height=5)
        pdf.ln(2)
    pdf.ln(2)


def build_requirement_review_pdf(review: RequirementReview, *, project_name: str = "") -> bytes:
    font_family, font_path = _pick_unicode_font()
    pdf = _ReviewPDF(font_family=font_family, font_path=font_path)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    payload = review.result_json if isinstance(review.result_json, dict) else {}
    sections = [(title, _normalize_items(payload.get(key))) for key, title in _SECTION_TITLES]
    issue_total = sum(len(items) for _, items in sections)

    pdf.set_body_font(16, bold=True)
    pdf.write_line("需求评估报告", height=10)
    pdf.set_body_font(11)
    pdf.write_line(f"项目：{project_name or review.project_id}", height=6)
    pdf.write_line(f"评审 ID：{review.id}", height=6)
    pdf.write_line(f"模型：{review.model_name}", height=6)
    pdf.write_line(f"时间：{review.created_at}", height=6)
    source = getattr(review, "source_filename", None) or "粘贴文本"
    pdf.write_line(f"来源：{source}", height=6)
    pdf.write_line(f"问题总数：{issue_total}", height=6)
    pdf.ln(2)

    pdf.set_body_font(12, bold=True)
    pdf.write_line("评估摘要", height=8)
    pdf.set_body_font(10)
    summary = "  |  ".join(f"{title} {len(items)}" for title, items in sections)
    pdf.write_line(summary, height=6)
    pdf.ln(3)

    pdf.set_body_font(13, bold=True)
    pdf.write_line("需求评估明细", height=8)
    pdf.ln(1)
    for title, items in sections:
        _render_issue_section(pdf, title, items)

    pdf.set_body_font(12, bold=True)
    pdf.write_line("附录：需求原文摘要", height=8)
    pdf.set_body_font(9)
    snapshot = _text(review.requirement_text or "")
    if not snapshot:
        pdf.write_line("（该记录未保存需求正文）")
    else:
        clipped = snapshot[:_SNAPSHOT_LIMIT]
        if len(snapshot) > _SNAPSHOT_LIMIT:
            clipped += "\n…（正文过长，已截断；完整内容请查看页面或 HTML 报告）"
        pdf.write_line(clipped, height=5)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
