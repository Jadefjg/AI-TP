"""Requirement review JSON parsing."""

import pytest

from backend.services.ai.json_utils import parse_json_payload, parse_requirement_review_response


def test_parse_json_payload_handles_markdown_fence():
    content = """说明如下：
```json
{"ambiguity_list": [], "miss_logic_list": [], "untestable_list": [], "biz_risk_list": []}
```"""
    payload = parse_json_payload(content)
    assert isinstance(payload, dict)


def test_parse_requirement_review_response_rejects_error_object():
    with pytest.raises(ValueError, match="无法理解"):
        parse_requirement_review_response('{"error":"无法理解输入内容，请提供清晰的需求描述。"}')


def test_parse_requirement_review_response_accepts_review_lists():
    payload = parse_requirement_review_response(
        '{"ambiguity_list":[{"pos":"A","level":"中","desc":"d","suggest":"s"}],'
        '"miss_logic_list":[],"untestable_list":[],"biz_risk_list":[]}'
    )
    assert len(payload["ambiguity_list"]) == 1
