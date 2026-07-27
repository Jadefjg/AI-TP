export type RequirementReviewSectionKey =
  | "ambiguity_list"
  | "miss_logic_list"
  | "untestable_list"
  | "biz_risk_list";

export const REQUIREMENT_REVIEW_SECTIONS: Array<{
  key: RequirementReviewSectionKey;
  title: string;
  description: string;
  color: string;
}> = [
  {
    key: "ambiguity_list",
    title: "需求歧义",
    description: "识别描述模糊、口径不一致或易产生误解的点",
    color: "arcoblue",
  },
  {
    key: "miss_logic_list",
    title: "逻辑缺失",
    description: "分析流程闭环、边界与异常场景是否完整合理",
    color: "orange",
  },
  {
    key: "untestable_list",
    title: "可测性缺陷",
    description: "判断需求是否可量化、可验证、可设计测试用例",
    color: "gray",
  },
  {
    key: "biz_risk_list",
    title: "业务风险",
    description: "提示潜在业务冲突、合规与上线风险",
    color: "red",
  },
];

export type RequirementReviewRow = {
  id: number;
  project_id: number;
  model_name: string;
  created_at: string;
  source_filename?: string | null;
  source_format?: string | null;
  requirement_text?: string;
  result_json: Record<string, unknown>;
};

export function reviewSourceLabel(row: Pick<RequirementReviewRow, "source_filename">) {
  return row.source_filename || "粘贴文本";
}

export function clipRequirementPreview(text: string | null | undefined, limit = 120) {
  const value = (text || "").replace(/\s+/g, " ").trim();
  if (!value) return "—";
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`;
}

export function countReviewIssues(result: Record<string, unknown> | undefined) {
  return REQUIREMENT_REVIEW_SECTIONS.reduce((sum, section) => {
    const items = result?.[section.key];
    return sum + (Array.isArray(items) ? items.length : 0);
  }, 0);
}
