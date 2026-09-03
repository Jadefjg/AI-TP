export type OpsPipelineStepKey =
  | "overview"
  | "schedule"
  | "dictionaries"
  | "alerts"
  | "audit"
  | "k6";

export type OpsPipelineStep = {
  key: OpsPipelineStepKey;
  label: string;
  short: string;
  hint: string;
  subtitle: string;
  badge: string;
  statusLabel: string;
  routeName: string;
  path: string;
  permission: string | string[];
};

export const OPS_PIPELINE_STEPS: OpsPipelineStep[] = [
  {
    key: "overview",
    label: "运维总览",
    short: "01",
    hint: "健康 · 队列 · Worker",
    subtitle: "健康评分、队列积压与 Worker 状态一目了然，异常可下钻到告警与审计。",
    badge: "AI · OPS",
    statusLabel: "运维域",
    routeName: "ops-overview",
    path: "/ops/overview",
    permission: ["ops.read", "system.read"],
  },
  {
    key: "schedule",
    label: "定时任务",
    short: "02",
    hint: "白名单调度",
    subtitle: "仅执行后端预注册 handler，禁止在页面输入 Shell 或 SQL。",
    badge: "AI · OPS",
    statusLabel: "调度就绪",
    routeName: "ops-schedule",
    path: "/ops/schedule",
    permission: "schedule.read",
  },
  {
    key: "dictionaries",
    label: "数据字典",
    short: "03",
    hint: "平台枚举",
    subtitle: "维护平台枚举与标签，供流水与运维模块复用。",
    badge: "AI · OPS",
    statusLabel: "字典就绪",
    routeName: "ops-dictionaries",
    path: "/ops/dictionaries",
    permission: "dict.read",
  },
  {
    key: "alerts",
    label: "告警通道",
    short: "04",
    hint: "钉钉 · 企微 · Webhook",
    subtitle: "观测通道配置状态；密钥只在系统配置中维护，本页不暴露密钥。",
    badge: "AI · OPS",
    statusLabel: "通道观测",
    routeName: "ops-alerts",
    path: "/ops/alerts",
    permission: ["ops.read", "settings.read"],
  },
  {
    key: "audit",
    label: "日志审计",
    short: "05",
    hint: "可追溯",
    subtitle: "只读查询为主；导出与留存清理需独立权限，禁止在界面篡改审计内容。",
    badge: "AI · OPS",
    statusLabel: "审计只读",
    routeName: "ops-audit",
    path: "/ops/audit",
    permission: "logs.read",
  },
  {
    key: "k6",
    label: "k6 节点",
    short: "06",
    hint: "分布式压测调度",
    subtitle: "对接本地节点或 HTTP Worker Agent，用于性能流水的分布式下发。",
    badge: "AI · PERF OPS",
    statusLabel: "调度就绪",
    routeName: "k6-workers",
    path: "/ops/k6-workers",
    permission: "worker.read",
  },
];

export const opsStepFromRoute = (route: {
  name?: string | symbol | null;
  path?: string;
}): OpsPipelineStep | null => {
  const name = typeof route.name === "string" ? route.name : "";
  const byName = OPS_PIPELINE_STEPS.find((step) => step.routeName === name);
  if (byName) return byName;
  const path = route.path || "";
  if (!path) return null;
  if (path === "/k6-workers" || path.startsWith("/k6-workers/")) {
    return OPS_PIPELINE_STEPS.find((step) => step.key === "k6") || null;
  }
  const matches = OPS_PIPELINE_STEPS.filter(
    (step) => path === step.path || path.startsWith(`${step.path}/`),
  );
  matches.sort((a, b) => b.path.length - a.path.length);
  return matches[0] || null;
};
