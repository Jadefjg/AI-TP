"""Typed hand-offs between Agent workflow steps."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, ValidationError

class AgentArtifactEnvelope(BaseModel):
    module_type: str
    payload: Any
    persisted_ids: list[int] = Field(default_factory=list)
    model: str | None = None


class RequirementInput(BaseModel):
    requirement_text: str = Field(min_length=1)
    source_filename: str | None = None

class CasesInput(BaseModel):
    requirement_text: str = Field(min_length=1)
    openapi_content: str | None = None

class ApiInput(BaseModel):
    case_info: str = Field(min_length=1)
    api_info: str = Field(min_length=1)

class PerfInput(BaseModel):
    biz_desc: str = Field(min_length=1)
    api_doc: str = ""

class SecurityInput(BaseModel):
    api_params: str = Field(min_length=1)


def _payload(result: dict[str, Any]) -> Any:
    return result.get("payload", result)


def _requirement_review_text(value: Any, original: str = "") -> str:
    """Render the reviewed/final requirement as explicit input for case generation."""
    if not isinstance(value, dict):
        return str(value or original)
    final_text = value.get("final_requirement") or value.get("final_requirement_text") or value.get("requirement_text")
    sections = []
    if final_text:
        sections.append(f"【最终需求】\n{final_text}")
    labels = (("ambiguity_list", "需求歧义"), ("miss_logic_list", "逻辑缺失"),
              ("untestable_list", "不可测试项"), ("biz_risk_list", "业务风险"))
    for key, label in labels:
        rows = value.get(key)
        if rows:
            sections.append(f"【{label}】\n{rows}")
    if not sections:
        return original or str(value)
    return "\n\n".join(str(x) for x in sections)


def build_step_input(module: str, *, run_input: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Convert a previous typed result into the next module's request contract."""
    value = _payload(result)
    text = value if isinstance(value, str) else str(value)
    base = dict(run_input)
    if module == "requirement_review":
        return RequirementInput(requirement_text=base.get("requirement_text") or text,
                                 source_filename=base.get("source_filename")).model_dump(exclude_none=True)
    if module == "functional_cases":
        reviewed = _requirement_review_text(value, base.get("requirement_text") or "")
        return CasesInput(requirement_text=reviewed,
                          openapi_content=base.get("openapi_content")).model_dump(exclude_none=True)
    if module == "api_automation":
        return ApiInput(case_info=base.get("case_info") or text,
                        api_info=base.get("api_info") or text).model_dump()
    if module == "perf_plan":
        return PerfInput(biz_desc=base.get("biz_desc") or text,
                         api_doc=base.get("api_doc") or text).model_dump()
    if module == "security_scan":
        return SecurityInput(api_params=base.get("api_params") or text).model_dump()
    raise ValueError(f"unsupported workflow module: {module}")


def validate_result(result: dict[str, Any], expected_module: str | None = None) -> AgentArtifactEnvelope:
    """Validate the persisted AI job envelope before handing it to another Agent."""
    envelope = AgentArtifactEnvelope.model_validate(result)
    if expected_module and envelope.module_type != expected_module:
        raise ValueError(f"artifact module mismatch: expected {expected_module}, got {envelope.module_type}")
    return envelope


def build_validated_handoff(module: str, *, run_input: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Return a serializable handoff envelope for persistence and replay."""
    envelope = validate_result(result)
    payload = build_step_input(module, run_input=run_input, result=result)
    return {"module_type": module, "source_module": envelope.module_type,
            "source_artifact_ids": envelope.persisted_ids, "input": payload}
