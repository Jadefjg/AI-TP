import type { AiTaskResult } from "../types";

/** Detect offline / stub / LLM-unavailable fallback completions. */
export const isAiFallbackResult = (result: Pick<AiTaskResult, "model" | "used_fallback">) => {
  if (result.used_fallback) return true;
  const model = (result.model || "").toLowerCase();
  return (
    model.includes("fallback") ||
    model.includes("stub") ||
    model.includes("local-analyzer") ||
    model === "manual" ||
    model === "discovery" ||
    model === "url-fetch"
  );
};

export const aiSuccessMessage = (
  result: Pick<AiTaskResult, "model" | "used_fallback">,
  successLabel: string,
) => {
  if (!isAiFallbackResult(result)) {
    return `${successLabel}（模型 ${result.model}）`;
  }
  // discovery/manual/url-fetch are intentional non-LLM paths — softer copy
  const model = (result.model || "").toLowerCase();
  if (model === "manual" || model === "discovery" || model === "url-fetch") {
    return `${successLabel}（来源 ${result.model}）`;
  }
  return `${successLabel}（当前为 Stub/离线兜底 · ${result.model}，配置有效 LLM Key 可提升质量）`;
};
