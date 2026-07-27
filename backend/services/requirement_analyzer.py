from __future__ import annotations

import re
from typing import Any

Issue = dict[str, str]

_LIST_PREFIX = re.compile(r"^(\d+[\.\)、]|[-*•]\s*)")

_VAGUE_TERMS = (
    "可能",
    "也许",
    "尽量",
    "适当",
    "相关",
    "等等",
    "类似",
    "友好",
    "美观",
    "合理",
    "优化",
    "快速",
    "高效",
    "及时",
    "较好",
    "良好",
    "一定程度",
    "视情况",
    "原则上",
)

_LOGIC_HINTS = ("如果", "当", "否则", "异常", "失败", "错误", "超时", "重试", "回滚", "边界", "为空")
_TESTABLE_HINTS = ("验收", "预期", "应当", "必须", "不超过", "至少", "最多", "指标", "成功率", "响应时间", "≤", "≥", "%")

# keyword, level, problem template, suggestion
_RISK_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("支付", "高", "涉及支付能力，需关注资金安全与状态一致性", "补充支付状态机、对账规则、失败重试与补单策略"),
    ("退款", "高", "涉及退款能力，需关注逆向资金与幂等", "明确退款条件、幂等键、部分退款与到账时效"),
    ("权限", "高", "涉及权限控制，需关注越权与最小权限", "补充鉴权点、角色矩阵、越权用例与审计日志"),
    ("角色", "中", "涉及角色能力，需关注授权边界", "明确角色职责、授权变更流程与互斥约束"),
    ("删除", "高", "涉及删除操作，需关注误删与不可恢复风险", "补充软删/硬删策略、二次确认、回收站与审计追踪"),
    ("资金", "高", "涉及资金相关能力，需关注账实一致", "补充资金流水、对账差异处理与补偿预案"),
    ("密码", "中", "涉及密码/凭证，需关注泄露与爆破风险", "明确加密存储、复杂度、锁定策略与重置流程"),
    ("token", "中", "涉及 token/会话凭证，需关注伪造与失效", "补充签发范围、过期刷新、吊销与传输安全要求"),
    ("审核", "中", "涉及审核流程，需关注误审与积压", "明确审核时效、升级规则、驳回原因与抽检指标"),
    ("上线", "中", "涉及上线发布，需关注回滚与灰度风险", "补充灰度策略、回滚条件、监控告警与发布检查清单"),
    ("并发", "中", "涉及并发场景，需关注竞态与一致性", "明确锁/幂等键、重复提交与数据覆盖规则"),
    ("同时", "中", "涉及同时操作，需关注竞态与覆盖", "补充并发冲突处理、最后写入策略与提示文案"),
)


def _line_body(line: str) -> str:
    return _LIST_PREFIX.sub("", line).strip()


def _has_quantitative_content(text: str) -> bool:
    if any(hint in text for hint in _TESTABLE_HINTS):
        return True
    if re.search(r"\d+\s*(%|ms|秒|分钟|小时|次|条|个|人|天)", text):
        return True
    body = _line_body(text) if "\n" not in text else text
    return bool(re.search(r"\d{2,}", body))


def _clip(text: str, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _line_context(lines: list[str], index: int) -> str:
    start = max(0, index - 1)
    end = min(len(lines), index + 2)
    return _clip(" / ".join(lines[start:end]))


def analyze_requirement_heuristic(text: str) -> dict[str, list[Issue]]:
    """Offline requirement review from document text (no external LLM)."""
    raw = (text or "").strip()
    if len(raw) < 10:
        return {
            "ambiguity_list": [
                {
                    "pos": "全文",
                    "level": "高",
                    "desc": "需求正文过短，无法开展有效评审",
                    "suggest": "补充完整业务流程、验收标准与异常场景",
                }
            ],
            "miss_logic_list": [],
            "untestable_list": [],
            "biz_risk_list": [],
        }

    lines = [line.strip() for line in re.split(r"[\n\r]+", raw) if line.strip()]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]

    ambiguity_list: list[Issue] = []
    miss_logic_list: list[Issue] = []
    untestable_list: list[Issue] = []
    biz_risk_list: list[Issue] = []

    for idx, line in enumerate(lines):
        hits = [term for term in _VAGUE_TERMS if term in line]
        if hits and not _has_quantitative_content(_line_body(line)):
            ambiguity_list.append(
                {
                    "pos": _line_context(lines, idx),
                    "level": "中",
                    "desc": f"表述含模糊词：{', '.join(hits[:4])}",
                    "suggest": "改为可验证的量化描述（频率、状态、角色、输入输出）",
                }
            )

    numbered = [line for line in lines if re.match(r"^(\d+[\.\)、]|[-*•])", line)]
    if len(lines) >= 8 and len(numbered) < 2:
        miss_logic_list.append(
            {
                "pos": "文档结构",
                "level": "中",
                "desc": "缺少清晰编号/步骤结构，主流程与分支不易对齐测试",
                "suggest": "按「前置条件-操作步骤-预期结果」或用户故事拆分条目",
            }
        )

    if len(raw) >= 100 and not any(hint in raw for hint in _LOGIC_HINTS):
        miss_logic_list.append(
            {
                "pos": "全文",
                "level": "高",
                "desc": "未描述异常、失败、超时或边界处理逻辑",
                "suggest": "补充错误码、重试/回滚策略、空值与越权等异常分支",
            }
        )

    if len(raw) >= 80 and not _has_quantitative_content(raw):
        untestable_list.append(
            {
                "pos": "验收标准",
                "level": "高",
                "desc": "缺少可量化验收指标（数值、百分比、时延、成功率等）",
                "suggest": "为关键能力补充明确验收口径，例如响应时间、成功率、数据范围",
            }
        )

    for para in paragraphs[:30]:
        if len(para) < 40:
            continue
        if not _has_quantitative_content(para):
            untestable_list.append(
                {
                    "pos": _clip(para[:80]),
                    "level": "中",
                    "desc": "段落缺少可验证的验收条件",
                    "suggest": "补充该场景的预期结果、判定规则与测试数据示例",
                }
            )
            if len(untestable_list) >= 5:
                break

    seen_risk: set[str] = set()
    keyword_hits: set[str] = set()
    for idx, line in enumerate(lines):
        body = _line_body(line)
        lower = line.lower()
        for keyword, level, risk_desc, suggest in _RISK_SPECS:
            if keyword not in line and keyword not in lower:
                continue
            fingerprint = f"{keyword}|{_clip(body, 72)}"
            if fingerprint in seen_risk:
                continue
            # Prefer keyword diversity; only allow extra hits for same keyword when still sparse.
            if keyword in keyword_hits and len(keyword_hits) < 3 and len(biz_risk_list) >= 3:
                continue
            if keyword in keyword_hits and len(biz_risk_list) >= 5:
                continue
            seen_risk.add(fingerprint)
            keyword_hits.add(keyword)
            biz_risk_list.append(
                {
                    "pos": _line_context(lines, idx),
                    "level": level,
                    "desc": f"{risk_desc}。命中原文：{_clip(body, 90)}",
                    "suggest": suggest,
                }
            )
            if len(biz_risk_list) >= 6:
                break
        if len(biz_risk_list) >= 6:
            break

    return _dedupe_payload(
        {
            "ambiguity_list": ambiguity_list[:8],
            "miss_logic_list": miss_logic_list[:6],
            "untestable_list": untestable_list[:8],
            "biz_risk_list": biz_risk_list[:6],
        }
    )


REVIEW_LIST_KEYS = ("ambiguity_list", "miss_logic_list", "untestable_list", "biz_risk_list")


def split_requirement_sections(text: str, max_chars: int = 8000) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    if not paragraphs:
        return [(text or "").strip()]
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for para in paragraphs:
        extra = len(para) + (2 if buffer else 0)
        if buffer and size + extra > max_chars:
            chunks.append("\n\n".join(buffer))
            buffer = [para]
            size = len(para)
        else:
            buffer.append(para)
            size += extra
    if buffer:
        chunks.append("\n\n".join(buffer))
    return chunks


def merge_review_payloads(*payloads: Any) -> dict[str, list[Issue]]:
    merged: dict[str, list[Issue]] = {key: [] for key in REVIEW_LIST_KEYS}
    seen: set[str] = set()
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in REVIEW_LIST_KEYS:
            for item in payload.get(key) or []:
                if not isinstance(item, dict):
                    continue
                fingerprint = f"{key}|{item.get('pos')}|{item.get('desc')}"
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                merged[key].append(item)
    return merged


def _dedupe_payload(payload: dict[str, list[Issue]]) -> dict[str, list[Issue]]:
    result: dict[str, list[Issue]] = {}
    for key, items in payload.items():
        seen: set[str] = set()
        unique: list[Issue] = []
        for item in items:
            fingerprint = f"{item.get('pos')}|{item.get('desc')}"
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique.append(item)
        result[key] = unique
    return result


def normalize_requirement_review_payload(
    payload: Any,
    requirement_text: str,
    *,
    offline_only: bool = True,
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    keys = REVIEW_LIST_KEYS
    total = sum(len(data.get(key) or []) for key in keys if isinstance(data.get(key), list))
    if total > 0:
        return {key: list(data.get(key) or []) for key in keys}
    if offline_only:
        return analyze_requirement_heuristic(requirement_text)
    return {key: [] for key in keys}
