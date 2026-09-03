import type { Permission, User } from "../../types";

export type PermissionTreeNode = {
  key: string;
  title: string;
  code?: string;
  description?: string | null;
  menuType: "module" | "permission";
  sort: number;
  permissionId?: number;
  children?: PermissionTreeNode[];
};

export const MODULE_LABELS: Record<string, string> = {
  dashboard: "首页",
  project: "项目管理",
  knowledge: "知识库",
  case: "用例管理",
  ai: "AI 模块",
  prompt: "AI Prompt",
  worker: "k6 节点",
  run: "测试运行",
  report: "测试报告",
  user: "用户管理",
  role: "角色管理",
  permission: "权限管理",
  logs: "操作日志",
  audit: "审计导出",
  org: "租户管理",
  billing: "账单管理",
  settings: "系统配置",
  system: "系统信息",
  workbench: "AI 工作台",
  integration: "CI 集成",
  ops: "运维管理",
  dict: "数据字典",
  schedule: "定时任务",
};

export const ROLE_TAG_COLORS = ["arcoblue", "purple", "pinkpurple", "orange", "green", "cyan"] as const;

export function moduleLabel(prefix: string): string {
  return MODULE_LABELS[prefix] ?? prefix;
}

export function roleTagColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash + name.charCodeAt(i) * (i + 1)) % ROLE_TAG_COLORS.length;
  }
  return ROLE_TAG_COLORS[hash] ?? "arcoblue";
}

export function buildPermissionTree(permissions: Permission[]): PermissionTreeNode[] {
  const groups = new Map<string, Permission[]>();
  for (const perm of permissions) {
    const prefix = perm.code.includes(".") ? perm.code.split(".")[0] : "other";
    const bucket = groups.get(prefix) ?? [];
    bucket.push(perm);
    groups.set(prefix, bucket);
  }

  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([prefix, items]) => ({
      key: `module-${prefix}`,
      title: moduleLabel(prefix),
      menuType: "module" as const,
      sort: 0,
      disableCheckbox: true,
      children: items
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((perm, index) => ({
          key: `perm-${perm.id}`,
          title: perm.description ? `${perm.code}（${perm.description}）` : perm.code,
          code: perm.code,
          description: perm.description,
          menuType: "permission" as const,
          sort: 100 - index,
          permissionId: perm.id,
        })),
    }));
}

export type UserFilterQuery = {
  id?: string;
  username?: string;
  displayName?: string;
  keyword?: string;
  activeOnly?: boolean | null;
};

export function filterUsers(users: User[], query: UserFilterQuery): User[] {
  const idRaw = query.id?.trim();
  const idFilter = idRaw ? Number(idRaw) : null;
  const username = query.username?.trim().toLowerCase() ?? "";
  const displayName = query.displayName?.trim().toLowerCase() ?? "";
  const keyword = query.keyword?.trim().toLowerCase() ?? "";

  return users.filter((user) => {
    if (idFilter != null && Number.isFinite(idFilter) && user.id !== idFilter) return false;
    if (username && !user.username.toLowerCase().includes(username)) return false;
    if (displayName && !(user.display_name ?? "").toLowerCase().includes(displayName)) return false;
    if (query.activeOnly === true && !user.is_active) return false;
    if (query.activeOnly === false && user.is_active) return false;
    if (keyword) {
      const haystack = [
        String(user.id),
        user.username,
        user.display_name ?? "",
        user.email ?? "",
        user.roles?.map((r) => r.name).join(" ") ?? "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(keyword)) return false;
    }
    return true;
  });
}

export function usersForRole(users: User[], roleId: number): User[] {
  return users.filter((user) => user.roles?.some((role) => role.id === roleId));
}

export function countUsersForRole(users: User[], roleId: number): number {
  return usersForRole(users, roleId).length;
}
