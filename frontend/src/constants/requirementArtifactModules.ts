import type { AiTaskResult, FunctionalCase } from "../types";
import { aiApi } from "../api/ai";

export type RequirementArtifactModule = "api_automation" | "perf_plan" | "security_scan";

export type ArtifactGenerateOptions = {
  caseId?: number | null;
  caseInfo?: string | null;
  apiDocExtra?: string | null;
};

export type RequirementArtifactModuleConfig = {
  key: RequirementArtifactModule;
  title: string;
  subtitle: string;
  routeName: string;
  path: string;
  generateLabel: string;
  projectAiTab?: string;
  nextStepKey?: "perf" | "security" | null;
  tips: Array<{ label: string; text: string }>;
  generate: (
    projectId: number,
    requirementText: string,
    options?: ArtifactGenerateOptions,
  ) => Promise<AiTaskResult>;
};

export const formatCaseInfoForApi = (row: FunctionalCase) => {
  const steps = Array.isArray(row.steps) ? row.steps.join(" -> ") : "";
  return [
    `用例 #${row.id}: ${row.title}`,
    row.module ? `模块: ${row.module}` : "",
    row.preconditions ? `前置: ${row.preconditions}` : "",
    steps ? `步骤: ${steps}` : "",
    row.expected ? `期望: ${row.expected}` : "",
  ]
    .filter(Boolean)
    .join("\n");
};

export const REQUIREMENT_ARTIFACT_MODULES: Record<
  RequirementArtifactModule,
  RequirementArtifactModuleConfig
> = {
  api_automation: {
    key: "api_automation",
    title: "接口 Agent",
    subtitle: "基于当前项目上下文，由 AI 生成接口自动化 DSL",
    routeName: "interface-management",
    path: "/interface-management",
    generateLabel: "AI 生成接口测试",
    nextStepKey: "perf",
    tips: [
      {
        label: "生成依据",
        text: "以当前项目为主（名称、来源、路径/部署 URL、描述），可选绑定功能用例与补充说明",
      },
      {
        label: "生成内容",
        text: "输出自研引擎 YAML DSL（请求、断言、说明），可直接入库为 api_automation 产物",
      },
      {
        label: "后续动作",
        text: "本页执行 DSL 后，可一键进入性能 Agent，用接口产物继续生成压测方案",
      },
    ],
    generate: (projectId, requirementText, options) => {
      const caseInfo =
        options?.caseInfo?.trim() ||
        `基于当前项目整体能力，覆盖主流程与异常断言，生成接口自动化场景。\n补充上下文：\n${requirementText}`;
      return aiApi.aiApiAutomation(projectId, {
        case_info: caseInfo,
        api_info: requirementText,
        case_id: options?.caseId ?? null,
      });
    },
  },
  perf_plan: {
    key: "perf_plan",
    title: "性能 Agent",
    subtitle: "基于当前项目上下文，由 AI 生成并下发 k6 压测方案",
    routeName: "perf-management",
    path: "/perf-management",
    generateLabel: "AI 生成压测方案",
    nextStepKey: "security",
    tips: [
      {
        label: "生成依据",
        text: "以当前项目为主（名称、来源、路径/部署 URL、描述），推荐引用接口 DSL 产物",
      },
      {
        label: "生成内容",
        text: "输出压测模式、并发阶梯、时长、接口权重与 RT/错误率预警阈值",
      },
      {
        label: "后续动作",
        text: "下发 k6 后，可继续进入安全 Agent，基于同一业务上下文生成扫描策略",
      },
    ],
    generate: (projectId, requirementText, options) => {
      const apiDoc = [requirementText, options?.apiDocExtra?.trim()]
        .filter(Boolean)
        .join("\n\n--- 接口 DSL 上下文 ---\n");
      return aiApi.aiPerfPlan(projectId, {
        biz_desc: `【来自项目上下文】请基于以下业务与接口上下文设计压测方案：\n${requirementText}`,
        api_doc: apiDoc,
      });
    },
  },
  security_scan: {
    key: "security_scan",
    title: "安全 Agent",
    subtitle: "基于当前项目：生成安全测试策略 → 执行扫描 → 查看 HTML/PDF 报告",
    routeName: "security-management",
    path: "/security-management",
    generateLabel: "AI 生成安全策略",
    nextStepKey: null,
    tips: [
      {
        label: "生成依据",
        text: "以当前项目为主（名称、来源、路径/部署 URL、描述），推荐引用接口 DSL",
      },
      {
        label: "生成内容",
        text: "输出漏洞类型、风险等级、测试 Payload 与扫描策略（可入库）",
      },
      {
        label: "执行与报告",
        text: "填写目标 URL 后发起扫描；完成后可下载 HTML / PDF 报告",
      },
    ],
    generate: (projectId, requirementText, options) => {
      const extra = options?.apiDocExtra?.trim();
      const body = extra
        ? `【来自项目上下文】请基于以下业务与接口 DSL 生成安全测试策略：\n${requirementText}\n\n--- 接口 DSL ---\n${extra}`
        : `【来自项目上下文】请基于以下业务上下文生成安全测试入参与扫描策略：\n${requirementText}`;
      return aiApi.aiSecurityScan(projectId, body);
    },
  },
};
