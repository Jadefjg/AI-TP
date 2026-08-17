import { DEFAULT_BASE_URL, DEFAULT_HEALTH_URL } from "./platformDefaults";
import type { Project } from "../types";

/** Prefer persisted project.base_url, then deployed code_root, else platform default. */
export function resolveProjectBaseUrl(project: Project | null | undefined): string {
  if (!project) return DEFAULT_BASE_URL;
  const stored = (project.base_url || "").trim().replace(/\/+$/, "");
  if (stored) return stored;
  const root = (project.code_root || "").trim().replace(/\/+$/, "");
  if (project.repo_source === "deployed" && /^https?:\/\//i.test(root)) {
    return root;
  }
  return DEFAULT_BASE_URL;
}

export function resolveProjectHealthUrl(project: Project | null | undefined): string {
  const base = resolveProjectBaseUrl(project);
  if (base === DEFAULT_BASE_URL) return DEFAULT_HEALTH_URL;
  return `${base}/system/health`;
}
