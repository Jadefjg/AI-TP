from __future__ import annotations

import html
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from backend.models.entities import SecurityScanJob

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
)

_STATUS_LABELS = {
    "passed": "通过",
    "completed": "已完成（发现风险）",
    "skipped": "已跳过",
    "failed": "失败",
    "error": "错误",
    "running": "执行中",
    "pending": "等待中",
}


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")


def _pick_unicode_font() -> tuple[str, str | None]:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return "SecuritySans", str(path)
    return "Helvetica", None


def _review_status(job: SecurityScanJob, index: int) -> str:
    reviews = job.finding_reviews if isinstance(job.finding_reviews, dict) else {}
    row = reviews.get(str(index)) or reviews.get(index)
    if isinstance(row, dict):
        return str(row.get("status") or "pending")
    return "pending"


def _payload_preview(item: dict[str, Any]) -> str:
    payload = item.get("test_payload")
    if payload is None:
        payload = item.get("payload")
    if payload is None:
        return "—"
    if isinstance(payload, (list, tuple)):
        snippet = list(payload)[:2]
        return _text(json.dumps(snippet, ensure_ascii=False))
    return _text(payload)[:400]


def _job_detail(job: SecurityScanJob) -> dict[str, Any]:
    return job.detail if isinstance(job.detail, dict) else {}


def _findings(job: SecurityScanJob) -> list[dict[str, Any]]:
    return [item for item in (job.findings or []) if isinstance(item, dict)]


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status or "—")


def _conclusion(job: SecurityScanJob, findings: list[dict[str, Any]], detail: dict[str, Any]) -> str:
    status = str(job.status or "")
    reason = str(detail.get("reason") or "").strip()
    tested = detail.get("tested_requests")
    if status == "passed" and not findings:
        if tested:
            return f"扫描已完成，共发起 {tested} 次探测请求，未发现可疑漏洞信号。目标在当前策略下通过安全门禁。"
        return "扫描已完成，未发现可疑漏洞信号。目标在当前策略下通过安全门禁。"
    if status == "completed" and findings:
        return f"扫描已完成，共发现 {len(findings)} 条可疑风险，请结合复核状态与 Payload 进一步确认。"
    if status == "skipped":
        return reason or "扫描被跳过：目标不可达、无可用策略，或外部引擎未安装。"
    if status in {"failed", "error"}:
        return reason or "扫描执行失败，请检查目标地址、引擎与执行日志。"
    if findings:
        return f"共记录 {len(findings)} 条发现项，请人工复核。"
    return reason or "本次扫描暂无漏洞明细，请结合执行摘要复核。"


def _summary_rows(job: SecurityScanJob, findings: list[dict[str, Any]], detail: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("任务 ID", str(job.id)),
        ("状态", _status_label(str(job.status or ""))),
        ("引擎", str(job.engine or "—")),
        ("目标 URL", str(job.target_url or "—")),
        ("发现项数", str(len(findings))),
    ]
    if job.artifact_id:
        rows.append(("策略产物", f"#{job.artifact_id}"))
    if job.run_id:
        rows.append(("关联 Run", f"#{job.run_id}"))
    if detail.get("tested_requests") is not None:
        rows.append(("探测请求数", str(detail.get("tested_requests"))))
    if detail.get("strategy_count") is not None:
        rows.append(("策略条目数", str(detail.get("strategy_count"))))
    if detail.get("baseline_status") is not None:
        rows.append(("基线 HTTP 状态", str(detail.get("baseline_status"))))
    if detail.get("baseline_body_len") is not None:
        rows.append(("基线响应长度", str(detail.get("baseline_body_len"))))
    engines = detail.get("engines")
    if isinstance(engines, list) and engines:
        rows.append(("实际引擎", ", ".join(str(x) for x in engines)))
    if detail.get("reason"):
        rows.append(("原因说明", str(detail.get("reason"))))
    errors = detail.get("errors")
    if isinstance(errors, list) and errors:
        rows.append(("请求错误", f"{len(errors)} 条（详见下方）"))
    return rows


class _SecurityPDF(FPDF):
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


def build_security_scan_html(job: SecurityScanJob, *, project_name: str = "") -> str:
    findings = _findings(job)
    detail = _job_detail(job)
    conclusion = _conclusion(job, findings, detail)
    status = str(job.status or "")
    status_class = {
        "passed": "ok",
        "completed": "warn",
        "skipped": "skip",
        "failed": "bad",
        "error": "bad",
    }.get(status, "skip")

    summary_html = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in _summary_rows(job, findings, detail)
    )

    finding_rows: list[str] = []
    for idx, item in enumerate(findings):
        review = _review_status(job, idx)
        signals = item.get("signals")
        if isinstance(signals, list):
            signals_text = ", ".join(str(s) for s in signals[:6])
        else:
            signals_text = _text(signals) if signals else "—"
        finding_rows.append(
            "<tr>"
            f"<td>{idx + 1}</td>"
            f"<td>{_esc(item.get('vul_type'))}</td>"
            f"<td><span class='risk'>{_esc(item.get('risk_level'))}</span></td>"
            f"<td>{_esc(item.get('param') or '—')}</td>"
            f"<td>{_esc(item.get('scan_strategy') or job.engine)}</td>"
            f"<td>{_esc(review)}</td>"
            f"<td>{_esc(item.get('http_status') or '—')}</td>"
            f"<td>{_esc(signals_text)}</td>"
            f"<td><pre class='payload'>{_esc(_payload_preview(item))}</pre></td>"
            f"<td><pre class='payload'>{_esc(_text(item.get('body_preview'))[:300] or '—')}</pre></td>"
            "</tr>"
        )

    if finding_rows:
        findings_block = f"""
<section class="card">
  <h2>漏洞明细（{len(findings)}）</h2>
  <table class="findings">
    <thead>
      <tr>
        <th>#</th><th>类型</th><th>等级</th><th>参数</th><th>策略</th>
        <th>复核</th><th>HTTP</th><th>信号</th><th>Payload</th><th>响应摘要</th>
      </tr>
    </thead>
    <tbody>{''.join(finding_rows)}</tbody>
  </table>
</section>"""
    else:
        empty_title = "未发现漏洞"
        empty_desc = conclusion
        if status == "skipped":
            empty_title = "扫描已跳过"
        elif status in {"failed", "error"}:
            empty_title = "扫描未产生有效结果"
        findings_block = f"""
<section class="card empty">
  <h2>{_esc(empty_title)}</h2>
  <p>{_esc(empty_desc)}</p>
  <ul>
    <li>通过：表示探测完成且未触发可疑响应差异 / 注入信号。</li>
    <li>若目标仅为健康检查接口，通常预期为通过。</li>
    <li>需要更强覆盖时，可补充 OpenAPI/业务参数，或启用 nuclei / ZAP 引擎。</li>
  </ul>
</section>"""

    errors = detail.get("errors") if isinstance(detail.get("errors"), list) else []
    errors_block = ""
    if errors:
        items = "".join(f"<li><code>{_esc(err)}</code></li>" for err in errors[:20])
        errors_block = f"""
<section class="card">
  <h2>请求异常（{len(errors)}）</h2>
  <ul class="errors">{items}</ul>
</section>"""

    created = getattr(job, "created_at", None)
    created_text = created.isoformat(sep=" ", timespec="seconds") if created else "—"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>安全扫描报告 #{job.id}</title>
<style>
body {{ font-family: "Sora", "PingFang SC", "Helvetica Neue", sans-serif; margin: 0; color: #0f172a;
  background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%); }}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 40px; }}
h1 {{ margin: 0 0 8px; font-size: 24px; }}
h2 {{ margin: 0 0 12px; font-size: 16px; }}
.meta {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; }}
.badge.ok {{ color: #047857; background: #d1fae5; }}
.badge.warn {{ color: #b45309; background: #ffedd5; }}
.badge.skip {{ color: #0369a1; background: #e0f2fe; }}
.badge.bad {{ color: #b91c1c; background: #fee2e2; }}
.card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px 18px; margin-top: 14px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04); }}
.card.empty {{ border-style: dashed; background: linear-gradient(180deg, #f0fdf4, #fff); }}
.card.empty ul {{ margin: 10px 0 0; padding-left: 18px; color: #475569; font-size: 13px; line-height: 1.6; }}
.conclusion {{ font-size: 14px; line-height: 1.65; color: #334155; }}
table.summary {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
table.summary th {{ width: 140px; text-align: left; color: #64748b; font-weight: 600; padding: 8px 10px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
table.summary td {{ padding: 8px 10px; border-bottom: 1px solid #f1f5f9; word-break: break-all; }}
table.findings {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
table.findings th, table.findings td {{ border: 1px solid #e2e8f0; padding: 8px; text-align: left; vertical-align: top; }}
table.findings th {{ background: #f8fafc; }}
.risk {{ background: #fff7e8; padding: 2px 6px; border-radius: 4px; }}
.payload {{ margin: 0; font-size: 11px; white-space: pre-wrap; max-width: 220px; font-family: ui-monospace, Menlo, monospace; }}
.errors {{ margin: 0; padding-left: 18px; font-size: 12px; color: #b91c1c; }}
</style></head><body>
<div class="wrap">
  <h1>安全扫描报告 #{job.id}</h1>
  <p class="meta">
    项目：{_esc(project_name or job.project_id)} ·
    创建时间：{_esc(created_text)} ·
    状态：<span class="badge {status_class}">{_esc(_status_label(status))}</span>
  </p>
  <section class="card">
    <h2>执行结论</h2>
    <p class="conclusion">{_esc(conclusion)}</p>
  </section>
  <section class="card">
    <h2>扫描摘要</h2>
    <table class="summary">{summary_html}</table>
  </section>
  {findings_block}
  {errors_block}
</div>
</body></html>"""


def build_security_scan_pdf(job: SecurityScanJob, *, project_name: str = "") -> bytes:
    font_family, font_path = _pick_unicode_font()
    pdf = _SecurityPDF(font_family=font_family, font_path=font_path)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    findings = _findings(job)
    detail = _job_detail(job)
    conclusion = _conclusion(job, findings, detail)

    pdf.set_body_font(16, bold=True)
    pdf.write_line("安全扫描报告", height=10)
    pdf.set_body_font(11)
    pdf.write_line(f"项目：{project_name or job.project_id}", height=6)
    for key, value in _summary_rows(job, findings, detail):
        pdf.write_line(f"{key}：{value}", height=6)
    pdf.ln(2)

    pdf.set_body_font(13, bold=True)
    pdf.write_line("执行结论", height=8)
    pdf.set_body_font(10)
    pdf.write_line(conclusion, height=5)
    pdf.ln(3)

    pdf.set_body_font(13, bold=True)
    pdf.write_line("漏洞明细", height=8)
    pdf.set_body_font(10)
    if not findings:
        pdf.write_line("本次无漏洞项。若状态为通过，表示探测完成且未触发可疑信号。")
        if detail.get("reason"):
            pdf.write_line(f"说明：{detail.get('reason')}", height=5)
    else:
        for idx, item in enumerate(findings, start=1):
            review = _review_status(job, idx - 1)
            pdf.set_body_font(10, bold=True)
            pdf.write_line(
                f"{idx}. [{item.get('risk_level') or '-'}] {item.get('vul_type') or 'unknown'}",
                height=5,
            )
            pdf.set_body_font(10)
            pdf.write_line(f"参数：{item.get('param') or '—'}", height=5)
            pdf.write_line(f"策略：{item.get('scan_strategy') or job.engine}", height=5)
            pdf.write_line(f"复核：{review}", height=5)
            pdf.write_line(f"HTTP：{item.get('http_status') or '—'}", height=5)
            pdf.write_line(f"Payload：{_payload_preview(item)}", height=5)
            preview = _text(item.get("body_preview"))[:240]
            if preview:
                pdf.write_line(f"响应摘要：{preview}", height=5)
            pdf.ln(2)

    errors = detail.get("errors") if isinstance(detail.get("errors"), list) else []
    if errors:
        pdf.set_body_font(13, bold=True)
        pdf.write_line("请求异常", height=8)
        pdf.set_body_font(10)
        for err in errors[:20]:
            pdf.write_line(f"- {_text(err)[:300]}", height=5)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
