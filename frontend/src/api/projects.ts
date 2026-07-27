import type { Project, Recipient } from "../types";
import { BASE_URL } from "./config";
import { req } from "./client";

export const projectsApi = {
  listProjects: () => req<Project[]>("/projects"),
  getProject: (projectId: number) => req<Project>(`/projects/${projectId}`),
  createProject: (body: {
    name: string;
    description?: string | null;
    code_root: string;
    repo_source: string;
    repo_branch?: string | null;
  }) => req<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  updateProject: (
    projectId: number,
    body: {
      name: string;
      description?: string | null;
      code_root: string;
      repo_source: string;
      repo_branch?: string | null;
    },
  ) =>
    req<Project>(`/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  listRecipients: (projectId: number) => req<Recipient[]>(`/projects/${projectId}/recipients`),
  addRecipient: (projectId: number, body: { email: string; display_name?: string | null }) =>
    req<Recipient>(`/projects/${projectId}/recipients`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteRecipient: (projectId: number, recipientId: number) =>
    req<{ ok: boolean }>(`/projects/${projectId}/recipients/${recipientId}`, { method: "DELETE" }),
  deleteProject: (projectId: number) =>
    req<{ deleted: boolean; project_id: number }>(`/projects/${projectId}`, { method: "DELETE" }),
  exportCasesUrl: (projectId: number) => `${BASE_URL}/projects/${projectId}/functional-cases/export`,
};
