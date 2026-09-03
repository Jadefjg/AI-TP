import { DEFAULT_HEALTH_URL, PLATFORM_API_BASE_URL } from "./platformDefaults";
import type { Project } from "../types";

/**
 * Prefer persisted project.base_url, then deployed code_root.
 * Returns empty string when unknown — callers must not silently hit the platform API as SUT.
 */
export function resolveProjectBaseUrl(project: Project | null | undefined): string {
  if (!project) return "";
  const stored = (project.base_url || "").trim().replace(/\/+$/, "");
  if (stored) return stored;
  const root = (project.code_root || "").trim().replace(/\/+$/, "");
  if (project.repo_source === "deployed" && /^https?:\/\//i.test(root)) {
    return root;
  }
  return "";
}

export function resolveProjectHealthUrl(project: Project | null | undefined): string {
  const base = resolveProjectBaseUrl(project);
  if (!base) return "";
  if (base === PLATFORM_API_BASE_URL) return DEFAULT_HEALTH_URL;
  return `${base.replace(/\/+$/, "")}/`;
}
