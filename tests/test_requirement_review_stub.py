"""Requirement review offline stub path."""

import json

from backend.services.ai.constants import MODULE_REQUIREMENT_REVIEW
from backend.services.ai.stubs import build_stub_payload


def test_stub_requirement_review_uses_document_text():
    content = build_stub_payload(
        system_prompt="sys",
        user_prompt="【待评审需求内容】\n用户支付后系统应尽量快速退款",
        profile="high",
        module_type=MODULE_REQUIREMENT_REVIEW,
    )
    payload = json.loads(content)
    total = sum(len(payload[key]) for key in payload)
    assert total >= 2
