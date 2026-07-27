import type { FunctionalCase, KnowledgeChunk, TestPlan, TestSuite } from "../types";
import { req } from "./client";

export const casesApi = {
  genCases: (projectId: number, requirementText: string) =>
    req<FunctionalCase[]>(
      `/projects/${projectId}/functional-cases/generate`,
      {
        method: "POST",
        body: JSON.stringify({ requirement_text: requirementText }),
      },
      { timeoutMs: 120_000 },
    ),
  genCasesAgent: (projectId: number, requirementText: string) =>
    req<{ cases: FunctionalCase[]; contexts: Array<Record<string, unknown>> }>(
      `/projects/${projectId}/functional-cases/generate-agent`,
      {
        method: "POST",
        body: JSON.stringify({ requirement_text: requirementText }),
      },
      { timeoutMs: 120_000 },
    ),
  listCases: (projectId: number, suiteId?: number) => {
    const q = suiteId != null ? `?suite_id=${suiteId}` : "";
    return req<FunctionalCase[]>(`/projects/${projectId}/functional-cases${q}`);
  },
  getCase: (projectId: number, caseId: number) =>
    req<FunctionalCase>(`/projects/${projectId}/functional-cases/${caseId}`),
  createCase: (
    projectId: number,
    body: {
      title: string;
      module?: string | null;
      preconditions?: string | null;
      steps?: string[];
      expected?: string | null;
      priority?: string | null;
      source_requirement?: string | null;
    },
  ) =>
    req<FunctionalCase>(`/projects/${projectId}/functional-cases`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateCase: (
    projectId: number,
    caseId: number,
    body: {
      title?: string;
      module?: string | null;
      preconditions?: string | null;
      steps?: string[];
      expected?: string | null;
      priority?: string | null;
    },
  ) =>
    req<FunctionalCase>(`/projects/${projectId}/functional-cases/${caseId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteCase: (projectId: number, caseId: number) =>
    req<{ deleted: boolean }>(`/projects/${projectId}/functional-cases/${caseId}`, { method: "DELETE" }),
  importCases: (projectId: number, cases: Array<Record<string, unknown>>) =>
    req<FunctionalCase[]>(`/projects/${projectId}/functional-cases/import`, {
      method: "POST",
      body: JSON.stringify({ cases }),
    }),
  importOpenApiCases: (projectId: number, openapiContent: string, persist = true) =>
    req<FunctionalCase[]>(`/projects/${projectId}/functional-cases/import-openapi`, {
      method: "POST",
      body: JSON.stringify({ openapi_content: openapiContent, persist }),
    }),
  listTestPlans: (projectId: number) => req<TestPlan[]>(`/projects/${projectId}/test-plans`),
  createTestPlan: (projectId: number, body: { name: string; description?: string | null; status?: string }) =>
    req<TestPlan>(`/projects/${projectId}/test-plans`, { method: "POST", body: JSON.stringify(body) }),
  deleteTestPlan: (projectId: number, planId: number) =>
    req<{ deleted: boolean }>(`/projects/${projectId}/test-plans/${planId}`, { method: "DELETE" }),
  listTestSuites: (projectId: number) => req<TestSuite[]>(`/projects/${projectId}/test-suites`),
  createTestSuite: (
    projectId: number,
    body: { name: string; description?: string | null; plan_id?: number | null },
  ) =>
    req<TestSuite>(`/projects/${projectId}/test-suites`, { method: "POST", body: JSON.stringify(body) }),
  deleteTestSuite: (projectId: number, suiteId: number) =>
    req<{ deleted: boolean }>(`/projects/${projectId}/test-suites/${suiteId}`, { method: "DELETE" }),
  assignSuiteCases: (projectId: number, suiteId: number, caseIds: number[]) =>
    req<FunctionalCase[]>(`/projects/${projectId}/test-suites/${suiteId}/cases`, {
      method: "PUT",
      body: JSON.stringify({ case_ids: caseIds }),
    }),
  addKnowledge: (projectId: number, body: { source: string; title?: string | null; content: string }) =>
    req<KnowledgeChunk[]>(`/projects/${projectId}/knowledge/chunks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listKnowledge: (projectId: number) => req<KnowledgeChunk[]>(`/projects/${projectId}/knowledge/chunks`),
  searchKnowledge: (projectId: number, query: string, topK = 5) =>
    req<{
      query: string;
      hits: Array<{ id: number; source: string; title: string | null; content: string; score: number | null }>;
    }>(`/projects/${projectId}/knowledge/search?q=${encodeURIComponent(query)}&top_k=${topK}`),
};
