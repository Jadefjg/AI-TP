import type { Permission, Role, User } from "../types";
import { req } from "./client";

export const rbacApi = {
  listUsers: () => req<User[]>("/admin/users"),
  createUser: (body: {
    username: string;
    display_name?: string | null;
    email?: string | null;
    password: string;
    is_active: boolean;
    organization_id?: number | null;
    role_names?: string[];
  }) => req<User>("/admin/users", { method: "POST", body: JSON.stringify(body) }),
  assignUserRoles: (userId: number, roleIds: number[]) =>
    req<User>(`/admin/users/${userId}/roles`, {
      method: "POST",
      body: JSON.stringify({ role_ids: roleIds }),
    }),
  updateUser: (
    userId: number,
    body: {
      organization_id?: number | null;
      is_active?: boolean;
      role_ids?: number[];
    },
  ) => req<User>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) }),
  batchUpdateUsers: (
    userIds: number[],
    updates: {
      organization_id?: number | null;
      is_active?: boolean;
      role_ids?: number[];
    },
  ) =>
    req<User[]>("/admin/users/batch-update", {
      method: "POST",
      body: JSON.stringify({ user_ids: userIds, updates }),
    }),
  listRoles: () => req<Role[]>("/admin/roles"),
  createRole: (body: { name: string; description?: string | null }) =>
    req<Role>("/admin/roles", { method: "POST", body: JSON.stringify(body) }),
  assignRolePermissions: (roleId: number, permissionIds: number[]) =>
    req<Role>(`/admin/roles/${roleId}/permissions`, {
      method: "POST",
      body: JSON.stringify({ permission_ids: permissionIds }),
    }),
  listPermissions: () => req<Permission[]>("/admin/permissions"),
  createPermission: (body: { code: string; description?: string | null }) =>
    req<Permission>("/admin/permissions", { method: "POST", body: JSON.stringify(body) }),
};
