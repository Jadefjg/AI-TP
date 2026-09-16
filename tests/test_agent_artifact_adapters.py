from backend.services.agents.artifact_adapters import build_step_input, validate_result


def test_typed_agent_handoffs():
    result = {"payload": {"cases": [{"title": "login"}]}}
    api = build_step_input("api_automation", run_input={}, result=result)
    assert api["case_info"] and api["api_info"]
    perf = build_step_input("perf_plan", run_input={"biz_desc": "checkout"}, result=result)
    assert perf["biz_desc"] == "checkout"


def test_all_agent_input_contracts():
    result = {"module_type": "requirement_review", "payload": {"risk": "high"}, "persisted_ids": [1]}
    assert validate_result(result).persisted_ids == [1]
    assert build_step_input("requirement_review", run_input={}, result=result)["requirement_text"]
    assert build_step_input("functional_cases", run_input={"requirement_text": "登录"}, result=result)["requirement_text"] == "登录"
    assert build_step_input("security_scan", run_input={}, result=result)["api_params"]


def test_validated_handoff_contains_provenance():
    from backend.services.agents.artifact_adapters import build_validated_handoff
    handoff = build_validated_handoff("perf_plan", run_input={}, result={"module_type": "api_automation", "payload": {"paths": ["/x"]}, "persisted_ids": [8]})
    assert handoff["source_artifact_ids"] == [8]
    assert handoff["input"]["api_doc"]


def test_cases_use_final_reviewed_requirement():
    result = {"module_type": "requirement_review", "payload": {
        "final_requirement": "用户必须完成二次验证后才能支付",
        "ambiguity_list": ["验证码有效期未定义"],
    }, "persisted_ids": [3]}
    handoff = build_step_input("functional_cases", run_input={"requirement_text": "旧需求"}, result=result)
    assert "二次验证" in handoff["requirement_text"]
    assert "旧需求" not in handoff["requirement_text"]
