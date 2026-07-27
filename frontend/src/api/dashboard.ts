import type {
  AiUsageSummary,
  DashboardOverview,
  DashboardRunTrends,
  DashboardSummary,
  SystemOverview,
} from "../types";
import { req } from "./client";

export const dashboardApi = {
  getDashboardOverview: (days = 7, organizationId?: number) => {
    const params = new URLSearchParams({ days: String(days) });
    if (organizationId != null) params.set("organization_id", String(organizationId));
    return req<DashboardOverview>(`/dashboard/overview?${params}`);
  },
  getDashboardSummary: () => req<DashboardSummary>("/dashboard/summary"),
  getDashboardRunTrends: (days = 7) => req<DashboardRunTrends>(`/dashboard/run-trends?days=${days}`),
  getSystemOverview: () => req<SystemOverview>("/system/overview"),
  getHealth: () => req<{ status: string }>("/system/health"),
  getAiUsageSummary: () => req<AiUsageSummary>("/ai/usage/summary"),
};
