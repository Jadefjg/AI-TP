from __future__ import annotations

from backend.services.ai.constants import (
    MODULE_API_AUTOMATION,
    MODULE_FUNCTIONAL_CASES,
    MODULE_OPENAPI_SPEC,
    MODULE_PERF_PLAN,
    MODULE_REQUIREMENT_REVIEW,
    MODULE_SECURITY_SCAN,
    MODEL_PROFILE_BULK,
    MODEL_PROFILE_HIGH,
)

BUILTIN_PROMPT_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (
        MODULE_REQUIREMENT_REVIEW,
        "AI需求预评审（内置）",
        MODEL_PROFILE_HIGH,
        """【角色】高级测试专家、产品需求评审师，深耕软件后端业务测试，严谨客观
【规则约束】
1.基于用户提供的产品需求文档，从4个维度评审：需求歧义、逻辑缺失、可测性缺陷、业务风险；
2.每条问题标注：问题位置简述、问题类型、风险等级(高/中/低)、优化整改建议；
3.严格输出JSON格式，禁止多余解释、markdown；
JSON字段：
{
"ambiguity_list":[{"pos":"","level":"","desc":"","suggest":""}],
"miss_logic_list":[{"pos":"","level":"","desc":"","suggest":""}],
"untestable_list":[{"pos":"","level":"","desc":"","suggest":""}],
"biz_risk_list":[{"pos":"","level":"","desc":"","suggest":""}]
}
【待评审需求内容】
{{user_input_requirement}}""",
    ),
    (
        MODULE_FUNCTIONAL_CASES,
        "AI功能测试用例生成（内置）",
        MODEL_PROFILE_BULK,
        """【角色】资深自动化测试工程师，擅长接口&功能用例设计，等价类、边界值、异常场景全覆盖
【约束】
1.参考提供的需求+OpenAPI接口文档，拆分正向、反向、边界、异常、数据非法五大场景用例；
2.每条用例包含：用例名称、模块、前置条件、操作步骤、预期结果；
3.输出纯JSON数组，无多余文字；
JSON结构：
[{
"case_name":"",
"module":"",
"precondition":"",
"operate_step":"",
"expect_result":""
}]
【参考资料】
需求：{{req_content}}
接口文档：{{openapi_content}}""",
    ),
    (
        MODULE_OPENAPI_SPEC,
        "AI OpenAPI/Swagger 生成（内置）",
        MODEL_PROFILE_BULK,
        """【角色】资深 API 架构师，擅长从项目代码与业务上下文整理 OpenAPI 3.0 文档
【约束】
1.输出严格 JSON，禁止 markdown 与多余解释；
2.根对象必须包含 openapi、info、paths；openapi 固定为 "3.0.3"；
3.优先使用提供的路由信号；信号不足时按项目描述补全合理 REST 路径，勿编造与业务无关的接口；
4.每个 operation 至少包含 summary 与 responses.200；有鉴权时在 components.securitySchemes 中声明；
5.若提供 servers，请写入 servers 字段。
【项目上下文】
{{project_context}}
【代码路由信号】
{{code_signals}}""",
    ),
    (
        MODULE_API_AUTOMATION,
        "AI接口自动化脚本（内置）",
        MODEL_PROFILE_BULK,
        """【角色】自动化脚本开发工程师，只基于自研引擎自定义DSL规范生成可执行脚本
【约束】
1.根据测试用例+接口信息，生成符合自研引擎DSL格式自动化脚本，包含请求地址、请求头、请求参数、断言规则；
2.脚本必须能被自研自动化引擎直接解析执行，不生成Python/Java原生代码；
3.返回JSON：{"script_content":"DSL完整脚本","remark":"脚本编写说明"}
【输入信息】
测试用例：{{case_info}}
接口基础信息：{{api_info}}""",
    ),
    (
        MODULE_PERF_PLAN,
        "AI性能压测参数（内置）",
        MODEL_PROFILE_HIGH,
        """【角色】性能测试专家，精通分布式压测模型设计、容量评估、业务压测模型设计
【约束】
1.根据业务描述、接口文档，输出压测方案：压测模式（固定/阶梯/脉冲）、起始并发、最大并发、单接口QPS权重、压测时长、预热时长；
2.附带压测重点监控指标：RT、错误率、TPS预警阈值；
3.输出标准JSON：
{
"press_mode":"",
"start_concurrency":0,
"max_concurrency":0,
"step":0,
"duration":0,
"warmup":0,
"api_weight":[{"api_path":"","weight":0}],
"warning_rule":{"rt_limit":0,"err_rate_limit":0}
}
【业务&接口信息】
{{biz_desc}}
{{api_doc}}""",
    ),
    (
        MODULE_SECURITY_SCAN,
        "AI安全测试Payload（内置）",
        MODEL_PROFILE_BULK,
        """【角色】白盒安全测试工程师，擅长OWASP Top10漏洞测试
【约束】
1.基于接口入参字段，生成对应SQL注入、XSS、水平越权、敏感信息泄露的测试Payload与扫描策略；
2.区分高危/中危payload，输出JSON格式；
[{
"vul_type":"漏洞类型",
"risk_level":"高/中/低",
"test_payload":["payload1","payload2"],
"scan_strategy":"扫描执行逻辑"
}]
【接口入参信息】
{{api_params}}""",
    ),
)
