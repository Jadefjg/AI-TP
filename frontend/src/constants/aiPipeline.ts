export const PIPELINE_SUITE_NAME = "智能流水 · 自动套件";

export type AiPipelineStepKey = "requirements" | "ui" | "interface" | "perf" | "security";

export type AiPipelineStep = {
  key: AiPipelineStepKey;
  label: string;
  short: string;
  hint: string;
  routeName: string;
  path: string;
};

export type PipelineHandoff = {
  projectId?: number | null;
  reviewId?: number | null;
  caseId?: number | null;
  artifactId?: number | null;
};

export const AI_PIPELINE_STEPS: AiPipelineStep[] = [
  {
    key: "requirements",
    label: "需求 Agent",
    short: "01",
    hint: "评审 · 可测性 · 转用例",
    routeName: "requirements",
    path: "/requirements",
  },
  {
    key: "ui",
    label: "UI Agent",
    short: "02",
    hint: "Playwright GUI Agent",
    routeName: "ui-management",
    path: "/ui-management",
  },
  {
    key: "interface",
    label: "接口 Agent",
    short: "03",
    hint: "DSL 生成与调试执行",
    routeName: "interface-management",
    path: "/interface-management",
  },
  {
    key: "perf",
    label: "性能 Agent",
    short: "04",
    hint: "压测方案 · k6 下发",
    routeName: "perf-management",
    path: "/perf-management",
  },
  {
    key: "security",
    label: "安全 Agent",
    short: "05",
    hint: "Payload · 扫描 · 报告",
    routeName: "security-management",
    path: "/security-management",
  },
];

/** Resolve pipeline step from the current vue-router location. */
export const pipelineStepFromRoute = (route: {
  name?: string | symbol | null;
  path?: string;
}): AiPipelineStep | null => {
  const name = typeof route.name === "string" ? route.name : "";
  const byName = AI_PIPELINE_STEPS.find((step) => step.routeName === name);
  if (byName) return byName;
  const path = route.path || "";
  if (!path) return null;
  if (path === "/cases" || path.startsWith("/cases/")) {
    return AI_PIPELINE_STEPS.find((step) => step.key === "requirements") || null;
  }
  const matches = AI_PIPELINE_STEPS.filter(
    (step) => path === step.path || path.startsWith(`${step.path}/`),
  );
  matches.sort((a, b) => b.path.length - a.path.length);
  return matches[0] || null;
};

export const AI_BUSY_MESSAGES = [
  "正在理解业务上下文…",
  "检索项目知识库命中片段…",
  "拆解场景与边界条件…",
  "编排测试建议与断言…",
  "几乎完成，正在整理结果…",
];

const PIPELINE_PROJECT_KEY = "ai-tp-pipeline-project-id";

export const pipelineRouteName = (key: AiPipelineStepKey) =>
  AI_PIPELINE_STEPS.find((step) => step.key === key)?.routeName || "requirements";

export const nextPipelineStep = (current: AiPipelineStepKey): AiPipelineStep | null => {
  const index = AI_PIPELINE_STEPS.findIndex((step) => step.key === current);
  if (index < 0 || index >= AI_PIPELINE_STEPS.length - 1) return null;
  return AI_PIPELINE_STEPS[index + 1];
};

export const buildPipelineQuery = (handoff: PipelineHandoff = {}) => {
  const query: Record<string, string> = {};
  if (handoff.projectId != null) query.projectId = String(handoff.projectId);
  if (handoff.reviewId != null) query.reviewId = String(handoff.reviewId);
  if (handoff.caseId != null) query.caseId = String(handoff.caseId);
  if (handoff.artifactId != null) query.artifactId = String(handoff.artifactId);
  return query;
};

export const parsePipelineQuery = (query: Record<string, unknown>): PipelineHandoff => {
  const toInt = (value: unknown) => {
    const n = Number(Array.isArray(value) ? value[0] : value);
    return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
  };
  return {
    projectId: toInt(query.projectId),
    reviewId: toInt(query.reviewId),
    caseId: toInt(query.caseId),
    artifactId: toInt(query.artifactId),
  };
};

export const rememberPipelineProjectId = (projectId: number | null | undefined) => {
  if (projectId == null || !Number.isFinite(projectId)) return;
  try {
    sessionStorage.setItem(PIPELINE_PROJECT_KEY, String(projectId));
  } catch {
    /* ignore */
  }
};

export const recalledPipelineProjectId = (): number | null => {
  try {
    const raw = sessionStorage.getItem(PIPELINE_PROJECT_KEY);
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
  } catch {
    return null;
  }
};
