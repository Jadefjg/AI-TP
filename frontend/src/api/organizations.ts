import type {
  BillingCheckoutResult,
  BillingInvoice,
  Organization,
  OrganizationMember,
  OrganizationQuota,
} from "../types";
import { downloadBlob, req } from "./client";

export const organizationsApi = {
  listOrganizations: () => req<Organization[]>("/organizations"),
  createOrganization: (body: {
    slug: string;
    name: string;
    description?: string | null;
    max_projects?: number;
    monthly_ai_token_quota?: number;
  }) => req<Organization>("/organizations", { method: "POST", body: JSON.stringify(body) }),
  updateOrganization: (
    orgId: number,
    body: {
      name?: string | null;
      description?: string | null;
      max_projects?: number;
      monthly_ai_token_quota?: number;
      is_active?: boolean;
    },
  ) => req<Organization>(`/organizations/${orgId}`, { method: "PATCH", body: JSON.stringify(body) }),
  getOrganization: (orgId: number) => req<Organization>(`/organizations/${orgId}`),
  getOrganizationQuota: (orgId: number) => req<OrganizationQuota>(`/organizations/${orgId}/quota`),
  listOrganizationMembers: (orgId: number) => req<OrganizationMember[]>(`/organizations/${orgId}/members`),
  addOrganizationMemberByRoles: (orgId: number, body: { user_id: number; role_names: string[] }) =>
    req<OrganizationMember>(`/organizations/${orgId}/members/by-role-names`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  removeOrganizationMember: (orgId: number, userId: number) =>
    req<{ ok: boolean }>(`/organizations/${orgId}/members/${userId}`, { method: "DELETE" }),
  listBillingInvoices: (orgId: number) => req<BillingInvoice[]>(`/organizations/${orgId}/billing/invoices`),
  generateBillingInvoice: (orgId: number, period?: string) => {
    const q = period ? `?period=${encodeURIComponent(period)}` : "";
    return req<BillingInvoice>(`/organizations/${orgId}/billing/invoices/generate${q}`, { method: "POST" });
  },
  downloadBillingInvoicePdf: (orgId: number, invoiceId: number) =>
    downloadBlob(`/organizations/${orgId}/billing/invoices/${invoiceId}/pdf`, `invoice-${invoiceId}.pdf`),
  createBillingCheckout: (
    orgId: number,
    body: { invoice_id: number; success_url?: string; cancel_url?: string },
  ) =>
    req<BillingCheckoutResult>(`/organizations/${orgId}/billing/checkout`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
