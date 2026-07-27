from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from backend.models.entities import ReportArtifact, TestRun, TestRunItem


def _esc(s: Any) -> str:
    text = "" if s is None else str(s)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.isoformat(sep=" ", timespec="seconds")


def _duration_text(started: datetime | None, finished: datetime | None) -> str:
    if not started or not finished:
        return "—"
    seconds = max(0.0, (finished - started).total_seconds())
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, rem = divmod(seconds, 60)
    return f"{int(minutes)} m {rem:.1f} s"


def _status_class(status: str) -> str:
    key = (status or "").lower()
    if key in {"passed", "completed"}:
        return "ok"
    if key in {"failed", "error"}:
        return "bad"
    if key in {"skipped", "cancelled"}:
        return "skip"
    if key == "running":
        return "run"
    return "muted"


def _item_reason(detail: dict | None) -> str:
    if not isinstance(detail, dict):
        return ""
    for key in ("reason", "error", "message"):
        value = detail.get(key)
        if value:
            return str(value)
    return ""


def _pre(content: str | None, *, empty: str = "（无输出）", log: bool = False) -> str:
    text = (content or "").strip()
    if not text:
        return f'<pre class="empty">{_esc(empty)}</pre>'
    cls = ' class="log"' if log else ' class="cmd"'
    return f"<pre{cls}>{_esc(text)}</pre>"


def _json_block(data: Any) -> str:
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        text = str(data)
    return f'<pre class="cmd">{_esc(text)}</pre>'


def _render_steps(steps: list[Any]) -> str:
    if not steps:
        return ""
    rows: list[str] = []
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            rows.append(
                f"<tr><td>{idx}</td><td colspan='3'><pre>{_esc(step)}</pre></td></tr>"
            )
            continue
        name = step.get("name") or step.get("title") or f"step-{step.get('index', idx)}"
        status = str(step.get("status") or "—")
        reason = step.get("reason") or step.get("error") or ""
        extra = {
            k: v
            for k, v in step.items()
            if k not in {"name", "title", "status", "reason", "error", "index"}
        }
        extra_html = _json_block(extra) if extra else "—"
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{_esc(name)}</td>"
            f"<td><span class='badge {_status_class(status)}'>{_esc(status)}</span></td>"
            f"<td>{_esc(reason) if reason else extra_html}</td>"
            "</tr>"
        )
    return (
        "<h4>步骤明细</h4>"
        "<table><thead><tr><th>#</th><th>步骤</th><th>状态</th><th>说明</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_artifacts(artifacts: list[Any]) -> str:
    if not artifacts:
        return ""
    blocks: list[str] = []
    for art in artifacts:
        if not isinstance(art, dict):
            blocks.append(_json_block(art))
            continue
        title = art.get("title") or f"artifact #{art.get('artifact_id', '—')}"
        status = str(art.get("status") or "—")
        reason = art.get("reason") or ""
        meta = (
            f"<p><strong>{_esc(title)}</strong> "
            f"<span class='badge {_status_class(status)}'>{_esc(status)}</span>"
            f" · case_id={_esc(art.get('case_id'))}"
            f" · artifact_id={_esc(art.get('artifact_id'))}</p>"
        )
        if reason:
            meta += f"<p class='reason'>原因：{_esc(reason)}</p>"
        steps_html = _render_steps(art.get("steps") or []) if isinstance(art.get("steps"), list) else ""
        stdout_html = ""
        if art.get("stdout"):
            stdout_html = f"<h5>产物 stdout</h5>{_pre(str(art.get('stdout')))}"
        blocks.append(f"<div class='subblock'>{meta}{steps_html}{stdout_html}</div>")
    return "<h4>脚本 / 产物结果</h4>" + "".join(blocks)


def _render_findings(findings: list[Any]) -> str:
    if not findings:
        return ""
    rows: list[str] = []
    for idx, item in enumerate(findings, start=1):
        if not isinstance(item, dict):
            rows.append(f"<tr><td>{idx}</td><td colspan='4'><pre>{_esc(item)}</pre></td></tr>")
            continue
        severity = item.get("severity") or item.get("level") or "—"
        title = item.get("title") or item.get("name") or item.get("rule") or f"finding-{idx}"
        target = item.get("target") or item.get("url") or item.get("path") or "—"
        detail = item.get("detail") or item.get("description") or item.get("message") or ""
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{_esc(severity)}</td>"
            f"<td>{_esc(title)}</td>"
            f"<td>{_esc(target)}</td>"
            f"<td>{_esc(detail)}</td>"
            "</tr>"
        )
    return (
        "<h4>安全发现</h4>"
        "<table><thead><tr><th>#</th><th>级别</th><th>标题</th><th>目标</th><th>说明</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_metrics(detail: dict[str, Any]) -> str:
    metrics = detail.get("summary_metrics") or detail.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in metrics.items()
    )
    return (
        "<h4>性能指标</h4>"
        f"<table><thead><tr><th>指标</th><th>值</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _render_detail(detail: dict | None) -> str:
    if not isinstance(detail, dict) or not detail:
        return "<p class='muted'>无额外 detail 数据</p>"

    parts: list[str] = []
    reason = _item_reason(detail)
    if reason:
        parts.append(f"<p class='reason'><strong>原因 / 说明：</strong>{_esc(reason)}</p>")

    highlight_keys = (
        "engine",
        "base_url",
        "script_count",
        "kind",
        "engines",
        "integrated_run",
        "time_series_source",
        "script_path",
    )
    meta_rows = []
    for key in highlight_keys:
        if key in detail and detail[key] not in (None, "", [], {}):
            meta_rows.append(f"<tr><td>{_esc(key)}</td><td>{_esc(detail[key])}</td></tr>")
    if meta_rows:
        parts.append(
            "<h4>执行上下文</h4>"
            f"<table><thead><tr><th>字段</th><th>值</th></tr></thead><tbody>{''.join(meta_rows)}</tbody></table>"
        )

    artifacts = detail.get("artifacts")
    if isinstance(artifacts, list):
        parts.append(_render_artifacts(artifacts))

    steps = detail.get("steps")
    if isinstance(steps, list) and "artifacts" not in detail:
        parts.append(_render_steps(steps))

    findings = detail.get("findings")
    if isinstance(findings, list):
        parts.append(_render_findings(findings))

    parts.append(_render_metrics(detail))

    reserved = {
        "reason",
        "error",
        "message",
        "artifacts",
        "steps",
        "findings",
        "summary_metrics",
        "metrics",
        *highlight_keys,
    }
    remainder = {k: v for k, v in detail.items() if k not in reserved}
    if remainder:
        parts.append("<h4>完整 detail（JSON）</h4>")
        parts.append(_json_block(remainder if remainder else detail))
    elif not any(
        [
            reason,
            meta_rows,
            isinstance(artifacts, list) and artifacts,
            isinstance(steps, list) and steps,
            isinstance(findings, list) and findings,
            isinstance(detail.get("summary_metrics") or detail.get("metrics"), dict),
        ]
    ):
        parts.append("<h4>完整 detail（JSON）</h4>")
        parts.append(_json_block(detail))

    return "".join(parts)


def _summary_counts(items: list[TestRunItem]) -> str:
    counter = Counter((item.status or "unknown").lower() for item in items)
    order = ["passed", "failed", "error", "skipped", "cancelled", "pending", "running"]
    chips = []
    for key in order:
        if key in counter:
            chips.append(
                f"<span class='stat {_status_class(key)}'><strong>{counter[key]}</strong> {_esc(_status_label(key))}</span>"
            )
    for key, count in sorted(counter.items()):
        if key not in order:
            chips.append(
                f"<span class='stat {_status_class(key)}'><strong>{count}</strong> {_esc(key)}</span>"
            )
    chips.append(f"<span class='stat muted'><strong>{len(items)}</strong> 总计</span>")
    return f"<div class='stats'>{''.join(chips)}</div>"


def _status_label(status: str) -> str:
    labels = {
        "passed": "通过",
        "failed": "失败",
        "error": "错误",
        "skipped": "跳过",
        "cancelled": "已取消",
        "pending": "等待中",
        "running": "执行中",
        "completed": "已完成",
    }
    key = (status or "").lower()
    return labels.get(key, status or "—")


def _kind_label(kind: str) -> str:
    labels = {
        "unit": "单元测试",
        "functional": "功能用例",
        "api": "接口测试",
        "perf_backend": "后端性能",
        "perf_frontend": "前端性能",
        "sec_backend": "后端安全",
        "sec_frontend": "前端安全",
        "ui": "UI 自动化",
    }
    return labels.get(kind or "", kind or "—")


def _suggest_for_item(item: TestRunItem) -> str:
    detail = item.detail if isinstance(item.detail, dict) else {}
    reason = _item_reason(detail)
    status = (item.status or "").lower()
    tips: list[str] = []
    if status == "skipped":
        tips.append("该项未实际执行，不代表被测系统通过或失败。")
        if "code_root" in reason or "不存在" in reason:
            tips.append("请在项目管理中修正「代码路径 / code_root」，确认目录存在且可读。")
        elif "未安装" in reason or "PATH" in reason or "not found" in reason.lower():
            tips.append("请在运行环境安装对应工具（如 pytest / k6 / bandit / playwright）并加入 PATH。")
        elif "未指定" in reason or "为空" in reason:
            tips.append("请先绑定测试套件 / 计划，或在启动 Run 时选择用例范围。")
        elif reason:
            tips.append(f"跳过原因：{reason}")
        else:
            tips.append("详情中未记录跳过原因，建议重新执行 Run 以采集完整日志。")
    elif status in {"failed", "error"}:
        tips.append("请结合下方 stdout / stderr 与 detail 定位失败点。")
        if reason:
            tips.append(f"系统记录原因：{reason}")
        if not (item.stdout or "").strip() and not (item.stderr or "").strip():
            tips.append("本次无命令输出；若为编排层失败，优先检查 detail 与项目配置。")
    elif status == "passed":
        tips.append("该项执行通过。")
    return " ".join(tips)


def _render_conclusion(run: TestRun, items: list[TestRunItem]) -> str:
    counter = Counter((item.status or "unknown").lower() for item in items)
    failed = counter.get("failed", 0) + counter.get("error", 0)
    skipped = counter.get("skipped", 0)
    passed = counter.get("passed", 0)
    total = len(items)

    if run.status == "cancelled":
        verdict = "运行已取消"
        tone = "skip"
    elif failed:
        verdict = "运行失败"
        tone = "bad"
    elif total and skipped == total:
        verdict = "全部跳过（未形成有效验证）"
        tone = "skip"
    elif run.status == "completed" and failed == 0:
        verdict = "运行完成"
        tone = "ok"
    else:
        verdict = f"状态：{run.status}"
        tone = "muted"

    bullets: list[str] = [
        f"共 {total} 项：通过 {passed}，失败/错误 {failed}，跳过 {skipped}。",
    ]
    if run.error_message:
        bullets.append(f"运行级错误：{run.error_message}")
    for item in items:
        tip = _suggest_for_item(item)
        if tip:
            bullets.append(f"{_kind_label(item.kind)}（{item.status}）：{tip}")

    lis = "".join(f"<li>{_esc(b)}</li>" for b in bullets)
    return f"""
<div class="card">
  <h2>结论与建议</h2>
  <p><span class="badge {tone}">{_esc(verdict)}</span></p>
  <ul class="advice">{lis}</ul>
</div>
"""


def _log_stats(text: str | None) -> str:
    raw = text or ""
    if not raw.strip():
        return "0 行 / 0 字符"
    lines = raw.count("\n") + (1 if raw and not raw.endswith("\n") else 0)
    return f"{lines} 行 / {len(raw)} 字符"


def _item_summary_row(item: TestRunItem, index: int) -> str:
    reason = _item_reason(item.detail if isinstance(item.detail, dict) else None)
    return (
        "<tr>"
        f"<td>{index}</td>"
        f"<td>{_esc(_kind_label(item.kind))}<div class='muted'><code>{_esc(item.kind)}</code></div></td>"
        f"<td><span class='badge {_status_class(item.status)}'>{_esc(_status_label(item.status))}</span>"
        f"<div class='muted'>{_esc(item.status)}</div></td>"
        f"<td>{'' if item.exit_code is None else _esc(item.exit_code)}</td>"
        f"<td>{_esc(reason) if reason else '—'}</td>"
        f"<td>{_duration_text(item.started_at, item.finished_at)}</td>"
        f"<td><pre class='cmd'>{_esc(item.command or '—')}</pre></td>"
        f"<td><a href='#item-{item.id}'>查看明细</a></td>"
        "</tr>"
    )


def _item_detail_block(item: TestRunItem, index: int) -> str:
    detail = item.detail if isinstance(item.detail, dict) else None
    advice = _suggest_for_item(item)
    advice_html = f"<p class='advice-box'><strong>建议：</strong>{_esc(advice)}</p>" if advice else ""
    return f"""
<section class="item" id="item-{item.id}">
  <h3>#{index} {_esc(_kind_label(item.kind))} · <span class="badge {_status_class(item.status)}">{_esc(_status_label(item.status))}</span></h3>
  <table class="meta">
    <tbody>
      <tr><th>类型</th><td>{_esc(item.kind)}</td></tr>
      <tr><th>状态</th><td>{_esc(item.status)}（{_esc(_status_label(item.status))}）</td></tr>
      <tr><th>退出码</th><td>{'—' if item.exit_code is None else _esc(item.exit_code)}</td></tr>
      <tr><th>命令</th><td><pre class="cmd">{_esc(item.command or '—')}</pre></td></tr>
      <tr><th>开始时间</th><td>{_esc(_fmt_dt(item.started_at))}</td></tr>
      <tr><th>结束时间</th><td>{_esc(_fmt_dt(item.finished_at))}</td></tr>
      <tr><th>耗时</th><td>{_esc(_duration_text(item.started_at, item.finished_at))}</td></tr>
      <tr><th>stdout 规模</th><td>{_esc(_log_stats(item.stdout))}</td></tr>
      <tr><th>stderr 规模</th><td>{_esc(_log_stats(item.stderr))}</td></tr>
    </tbody>
  </table>
  {advice_html}
  <h4>执行详情</h4>
  {_render_detail(detail)}
  <h4>stdout</h4>
  {_pre(item.stdout, empty="（无输出 — 跳过/编排层失败时常见）", log=True)}
  <h4>stderr</h4>
  {_pre(item.stderr, empty="（无输出）", log=True)}
  <h4>原始 detail（JSON）</h4>
  {_json_block(detail if detail is not None else {})}
</section>
"""


def build_html_report(db: Session, run_id: int) -> ReportArtifact:
    from datetime import timezone

    run = (
        db.query(TestRun)
        .options(
            selectinload(TestRun.items),
            selectinload(TestRun.project),
            selectinload(TestRun.execution_job),
        )
        .filter(TestRun.id == run_id)
        .one()
    )

    items = sorted(run.items or [], key=lambda x: x.id)
    job = run.execution_job
    job_html = "—"
    if job:
        job_html = (
            f"#{job.id} · <span class='badge {_status_class(job.status)}'>{_esc(_status_label(job.status))}</span>"
            f" · 尝试 {job.attempt_count}/{job.max_attempts}"
        )
        if job.last_error:
            job_html += f"<div class='reason'>队列错误：{_esc(job.last_error)}</div>"

    error_html = ""
    if run.error_message:
        error_html = f"<p class='reason'><strong>运行错误：</strong>{_esc(run.error_message)}</p>"

    rows = [_item_summary_row(item, idx) for idx, item in enumerate(items, start=1)]
    details = [_item_detail_block(item, idx) for idx, item in enumerate(items, start=1)]
    if not details:
        details = ["<p class='muted'>本次运行没有执行项。</p>"]

    generated_at = _fmt_dt(datetime.now(timezone.utc))

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>测试报告 #{run.id}</title>
<style>
:root {{
  --bg: #f6f8fb;
  --card: #ffffff;
  --line: #d9e2ec;
  --text: #1f2933;
  --muted: #627d98;
  --ok: #0f7b3a;
  --bad: #b00020;
  --skip: #6b7280;
  --run: #0b6bcb;
}}
body {{
  font-family: "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  margin: 0;
  padding: 24px;
  color: var(--text);
  background: linear-gradient(180deg, #eef3f8 0%, var(--bg) 240px);
}}
h1, h2, h3, h4, h5 {{ margin: 0 0 12px; }}
h1 {{ font-size: 28px; }}
h2 {{ margin-top: 0; font-size: 20px; }}
h3 {{ font-size: 18px; }}
h4 {{ margin-top: 16px; font-size: 15px; color: #334e68; }}
p {{ margin: 8px 0; }}
ul.advice {{ margin: 8px 0 0 18px; padding: 0; line-height: 1.6; }}
.card {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
}}
.meta-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 18px;
}}
.meta-grid div {{
  padding: 8px 10px;
  background: #f8fafc;
  border-radius: 8px;
}}
.meta-grid .label {{
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 4px;
}}
table {{ border-collapse: collapse; width: 100%; background: #fff; }}
th, td {{ border: 1px solid var(--line); padding: 8px 10px; vertical-align: top; text-align: left; }}
th {{ background: #f0f4f8; }}
table.meta th {{ width: 140px; }}
pre {{
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  max-height: 420px;
  overflow: auto;
  background: #f0f4f8;
  color: #1f2933;
  border: 1px solid #d9e2ec;
}}
pre.cmd {{
  display: inline-block;
  max-width: 100%;
  max-height: none;
}}
pre.log {{
  background: #0b1220;
  color: #e2e8f0;
  border: 1px solid #1e293b;
}}
pre.empty {{
  color: var(--muted);
  font-style: italic;
  background: #f8fafc;
  border: 1px solid #e4ebf2;
  max-height: none;
}}
.badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: #e4ebf2;
  color: #334e68;
}}
.badge.ok {{ background: #d9f7e5; color: var(--ok); }}
.badge.bad {{ background: #ffe1e6; color: var(--bad); }}
.badge.skip {{ background: #e5e7eb; color: var(--skip); }}
.badge.run {{ background: #dcebff; color: var(--run); }}
.stats {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px; }}
.stat {{
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #f0f4f8;
  color: #334e68;
  font-size: 13px;
}}
.stat.ok {{ background: #d9f7e5; color: var(--ok); }}
.stat.bad {{ background: #ffe1e6; color: var(--bad); }}
.stat.skip {{ background: #e5e7eb; color: var(--skip); }}
.reason {{
  color: #92400e;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  padding: 8px 10px;
}}
.advice-box {{
  color: #1e3a5f;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 8px 10px;
}}
.muted {{ color: var(--muted); font-size: 12px; }}
.item {{ margin-top: 18px; padding-top: 8px; border-top: 1px dashed var(--line); }}
.subblock {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 0;
  background: #fcfdff;
}}
code {{ background: #f0f4f8; padding: 1px 5px; border-radius: 4px; }}
a {{ color: #0b6bcb; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.footer {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
</style></head><body>
  <div class="card">
    <h1>测试报告</h1>
    <div class="meta-grid">
      <div><span class="label">项目</span><strong>{_esc(run.project.name)}</strong>（id={run.project.id}）</div>
      <div><span class="label">运行</span>#{run.id} · <span class="badge {_status_class(run.status)}">{_esc(_status_label(run.status))}</span></div>
      <div><span class="label">创建时间</span>{_esc(_fmt_dt(run.created_at))}</div>
      <div><span class="label">完成时间</span>{_esc(_fmt_dt(run.completed_at))}</div>
      <div><span class="label">总耗时</span>{_esc(_duration_text(run.created_at, run.completed_at))}</div>
      <div><span class="label">队列任务</span>{job_html}</div>
      <div><span class="label">代码路径</span><code>{_esc(run.project.code_root)}</code></div>
      <div><span class="label">报告生成时间</span>{_esc(generated_at)} UTC</div>
    </div>
    {error_html}
    {_summary_counts(items)}
  </div>

  {_render_conclusion(run, items)}

  <div class="card">
    <h2>摘要</h2>
    <table>
      <thead>
        <tr>
          <th>#</th><th>类型</th><th>状态</th><th>退出码</th>
          <th>原因 / 说明</th><th>耗时</th><th>命令</th><th>明细</th>
        </tr>
      </thead>
      <tbody>{''.join(rows) if rows else '<tr><td colspan="8">无执行项</td></tr>'}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>明细</h2>
    <p class="muted">含跳过原因、执行上下文、stdout/stderr 与原始 detail JSON，便于排查与复盘。</p>
    {''.join(details)}
  </div>
  <p class="footer">AI-TP 自动生成 · Run #{run.id}</p>
</body></html>"""

    report = ReportArtifact(run_id=run.id, format="html", content=html)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
