export const PIPELINE_SUITE_NAME = "智能流水 · 自动套件";

export type AiPipelineStepKey =
  | "requirements"
  | "cases"
  | "interface"
  | "perf"
  | "security";

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
    label: "需求分析",
    short: "01",
    hint: "文档理解 · 模糊点 · 可测性",
    routeName: "requirements",
    path: "/requirements",
  },
  {
    key: "cases",
    label: "测试用例",
    short: "02",
    hint: "Agent 扩写场景与边界",
    routeName: "cases",
    path: "/cases",
  },
  {
    key: "interface",
    label: "接口测试",
    short: "03",
    hint: "DSL 生成与调试执行",
    routeName: "interface-management",
    path: "/interface-management",
  },
  {
    key: "perf",
    label: "性能测试",
    short: "04",
    hint: "压测方案 · k6 下发",
    routeName: "perf-management",
    path: "/perf-management",
  },
  {
    key: "security",
    label: "安全测试",
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
  // Prefer longest path match to avoid prefix collisions.
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
