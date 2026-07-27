"""Requirement heuristic analysis (offline / no LLM)."""

from backend.services.requirement_analyzer import (
    analyze_requirement_heuristic,
    merge_review_payloads,
    normalize_requirement_review_payload,
    split_requirement_sections,
)


SAMPLE_REQUIREMENT = """
UGC 社区 1.2 分支需求

1. 用户发布帖子时，系统应尽量保证内容审核及时完成。
2. 支持点赞、评论与分享，体验需友好美观。
3. 用户可申请删除自己的帖子，管理员可批量处理。
4. 涉及支付打赏与退款，需保证资金安全。
5. 高峰期可能同时有大量用户并发发帖。
""".strip()


def test_analyze_requirement_heuristic_finds_issues():
    result = analyze_requirement_heuristic(SAMPLE_REQUIREMENT)
    assert len(result["ambiguity_list"]) >= 1
    assert len(result["biz_risk_list"]) >= 1
    assert all(key in result for key in ("miss_logic_list", "untestable_list"))


def test_biz_risk_issues_are_distinct():
    text = """
1. 用户发布帖子需要权限校验。
2. 管理员可删除违规内容。
3. 支持支付打赏能力。
4. 用户可申请退款。
5. 涉及资金结算对账。
6. 审核人员需及时处理积压。
""".strip()
    risks = analyze_requirement_heuristic(text)["biz_risk_list"]
    assert len(risks) >= 3
    descs = [item["desc"] for item in risks]
    suggests = [item["suggest"] for item in risks]
    assert len(set(descs)) == len(descs)
    assert len(set(suggests)) >= 2
    assert any("命中原文" in desc for desc in descs)


def test_normalize_fills_empty_stub_payload():
    normalized = normalize_requirement_review_payload({"message": "stub response"}, SAMPLE_REQUIREMENT)
    total = sum(len(normalized[key]) for key in normalized)
    assert total >= 3


def test_normalize_keeps_nonempty_llm_payload():
    llm_payload = {
        "ambiguity_list": [{"pos": "A", "level": "低", "desc": "x", "suggest": "y"}],
        "miss_logic_list": [],
        "untestable_list": [],
        "biz_risk_list": [],
    }
    normalized = normalize_requirement_review_payload(llm_payload, SAMPLE_REQUIREMENT)
    assert len(normalized["ambiguity_list"]) == 1
    assert normalized["ambiguity_list"][0]["pos"] == "A"


def test_short_requirement_reports_gap():
    result = analyze_requirement_heuristic("太短")
    assert len(result["ambiguity_list"]) == 1


def test_normalize_skips_heuristic_for_online_empty_payload():
    normalized = normalize_requirement_review_payload(
        {"message": "ok"}, SAMPLE_REQUIREMENT, offline_only=False
    )
    assert all(len(normalized[key]) == 0 for key in normalized)


def test_merge_review_payloads_dedupes():
    a = {
        "ambiguity_list": [{"pos": "A", "level": "中", "desc": "x", "suggest": "y"}],
        "miss_logic_list": [],
        "untestable_list": [],
        "biz_risk_list": [],
    }
    b = {
        "ambiguity_list": [
            {"pos": "A", "level": "中", "desc": "x", "suggest": "y"},
            {"pos": "B", "level": "低", "desc": "z", "suggest": "w"},
        ],
        "miss_logic_list": [],
        "untestable_list": [],
        "biz_risk_list": [],
    }
    merged = merge_review_payloads(a, b)
    assert len(merged["ambiguity_list"]) == 2


def test_split_requirement_sections():
    text = "\n\n".join(f"段落{i}：" + ("内容" * 200) for i in range(10))
    sections = split_requirement_sections(text, 1500)
    assert len(sections) >= 2
