import { computed, inject, provide, ref, type InjectionKey, type Ref } from "vue";
import { rbacApi } from "../../api/rbac";
import { organizationsApi } from "../../api/organizations";
import { usePlatformStore } from "../../state/platform";
import type { Organization, Permission, Role, User } from "../../types";

export type RbacDataContext = {
  users: Ref<User[]>;
  roles: Ref<Role[]>;
  permissions: Ref<Permission[]>;
  organizations: Ref<Organization[]>;
  canAccess: Ref<boolean>;
  orgNameById: Ref<Map<number, string>>;
  orgLabel: (orgId: number | null | undefined) => string;
  load: () => Promise<void>;
  refreshOrganizations: () => Promise<void>;
  upsertOrganization: (org: Organization) => void;
};

const RBAC_DATA_KEY: InjectionKey<RbacDataContext> = Symbol("rbac-data");

export function provideRbacData() {
  const store = usePlatformStore();
  const users = ref<User[]>([]);
  const roles = ref<Role[]>([]);
  const permissions = ref<Permission[]>([]);
  const organizations = ref<Organization[]>([]);

  const canAccess = computed(() =>
    store.hasAnyPermission(["user.manage", "role.manage", "permission.manage", "org.read"]),
  );

  const orgNameById = computed(() => {
    const map = new Map<number, string>();
    for (const org of organizations.value) {
      map.set(org.id, org.name);
    }
    return map;
  });

  const orgLabel = (orgId: number | null | undefined) => {
    if (orgId == null) return "平台";
    return orgNameById.value.get(orgId) ?? `租户 #${orgId}`;
  };

  const canLoadOrganizations = () =>
    store.hasPermission("org.read") || store.hasPermission("org.manage");

  const refreshOrganizations = async () => {
    if (!canLoadOrganizations()) {
      organizations.value = [];
      return;
    }
    organizations.value = await organizationsApi.listOrganizations();
  };

  const upsertOrganization = (org: Organization) => {
    const index = organizations.value.findIndex((item) => item.id === org.id);
    if (index >= 0) {
      organizations.value[index] = org;
      return;
    }
    organizations.value = [...organizations.value, org].sort((a, b) => a.id - b.id);
  };

  const load = async () => {
    await store.wrap(async () => {
      const tasks: Promise<void>[] = [];
      if (store.hasPermission("user.manage")) {
        tasks.push(rbacApi.listUsers().then((res) => (users.value = res)));
      } else {
        users.value = [];
      }
      if (store.hasPermission("role.manage")) {
        tasks.push(rbacApi.listRoles().then((res) => (roles.value = res)));
      } else {
        roles.value = [];
      }
      if (store.hasPermission("permission.manage")) {
        tasks.push(rbacApi.listPermissions().then((res) => (permissions.value = res)));
      } else {
        permissions.value = [];
      }
      if (canLoadOrganizations()) {
        tasks.push(refreshOrganizations());
      } else {
        organizations.value = [];
      }
      await Promise.all(tasks);
      store.setOut({
        users: users.value.length,
        roles: roles.value.length,
        permissions: permissions.value.length,
      });
    });
  };

  const ctx: RbacDataContext = {
    users,
    roles,
    permissions,
    organizations,
    canAccess,
    orgNameById,
    orgLabel,
    load,
    refreshOrganizations,
    upsertOrganization,
  };

  provide(RBAC_DATA_KEY, ctx);
  return ctx;
}

export function useRbacData() {
  const ctx = inject(RBAC_DATA_KEY);
  if (!ctx) {
    throw new Error("useRbacData must be used within SystemUsersLayout");
  }
  return ctx;
}
