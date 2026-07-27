<script setup lang="ts">
import { IconPlus, IconRefresh } from "@arco-design/web-vue/es/icon";
import { Message } from "@arco-design/web-vue";
import { computed, reactive, ref, watch } from "vue";
import { organizationsApi } from "../../api/organizations";
import { rbacApi } from "../../api/rbac";
import { listTablePagination } from "../../constants/listPagination";
import { usePlatformStore } from "../../state/platform";
import type { Organization, OrganizationMember } from "../../types";
import { useRbacData } from "./useRbacData";

const store = usePlatformStore();
const tablePagination = listTablePagination(10);
const { users, roles, organizations, load, refreshOrganizations, upsertOrganization } = useRbacData();

const selectedKey = ref<string>("platform");
const detailTab = ref("info");
const members = ref<OrganizationMember[]>([]);
const createVisible = ref(false);
const addUserVisible = ref(false);
const addUserMode = ref<"existing" | "create">("existing");

const memberForm = reactive({
  user_id: undefined as number | undefined,
  role_names: [] as string[],
});

const createUserForm = reactive({
  username: "",
  display_name: "",
  email: "",
  password: "",
  is_active: true,
  role_names: [] as string[],
});

const orgForm = reactive({
  name: "",
  slug: "",
  description: "",
  max_projects: 100,
  monthly_ai_token_quota: 500_000,
  is_active: true,
});

const createForm = reactive({
  name: "",
  slug: "",
  description: "",
  max_projects: 100,
  monthly_ai_token_quota: 500_000,
});

const canManageOrg = computed(() => store.hasPermission("org.manage"));
const canReadMembers = computed(() => store.hasPermission("org.member.read"));
const canManageMembers = computed(() => store.hasPermission("org.member.manage"));
const canCreateUser = computed(() => store.hasPermission("user.manage"));
const canAddUserHere = computed(() => {
  if (selectedKey.value === "platform") return canCreateUser.value;
  return canManageMembers.value || canCreateUser.value;
});

const roleOptions = computed(() => roles.value.map((r) => ({ value: r.name, label: r.name })));

const defaultRoleNames = () => {
  const member = roles.value.find((r) => r.name === "member");
  if (member) return [member.name];
  if (roles.value.length) return [roles.value[0].name];
  return ["member"];
};

const bindableUsers = computed(() => {
  if (selectedKey.value === "platform") {
    const platformIds = new Set(platformUsers.value.map((u) => u.id));
    return users.value.filter((u) => !platformIds.has(u.id));
  }
  const memberIds = new Set(members.value.map((m) => m.user_id));
  return users.value.filter((u) => !memberIds.has(u.id));
});

const expandedKeys = ref<string[]>(["platform"]);

const treeData = computed(() => [
  {
    key: "platform",
    title: "平台",
    children: organizations.value.map((org) => ({
      key: `org-${org.id}`,
      title: org.name,
      orgId: org.id,
    })),
  },
]);

const treeRenderKey = computed(() =>
  organizations.value.map((org) => `${org.id}:${org.name}`).join("|") || "empty",
);

const selectedOrgId = computed(() => {
  if (!selectedKey.value.startsWith("org-")) return null;
  return Number(selectedKey.value.replace("org-", ""));
});

const selectedOrg = computed(() =>
  selectedOrgId.value != null
    ? organizations.value.find((o) => o.id === selectedOrgId.value) ?? null
    : null,
);

const platformUsers = computed(() => users.value.filter((u) => u.organization_id == null));

const memberColumns = [
  { title: "用户 ID", dataIndex: "user_id", width: 90 },
  { title: "用户名", dataIndex: "username", width: 140 },
  { title: "昵称", dataIndex: "display_name" },
  { title: "邮箱", dataIndex: "email", ellipsis: true },
  { title: "角色", slotName: "roles" },
  { title: "状态", slotName: "active", width: 90 },
];

const platformUserColumns = [
  { title: "用户 ID", dataIndex: "id", width: 90 },
  { title: "用户名", dataIndex: "username", width: 140 },
  { title: "昵称", dataIndex: "display_name" },
  { title: "邮箱", dataIndex: "email" },
  { title: "状态", slotName: "active", width: 90 },
];

const syncOrgForm = (org: Organization | null) => {
  if (!org) {
    orgForm.name = "";
    orgForm.slug = "";
    orgForm.description = "";
    orgForm.max_projects = 100;
    orgForm.monthly_ai_token_quota = 500_000;
    orgForm.is_active = true;
    return;
  }
  orgForm.name = org.name;
  orgForm.slug = org.slug;
  orgForm.description = org.description ?? "";
  orgForm.max_projects = org.max_projects;
  orgForm.monthly_ai_token_quota = org.monthly_ai_token_quota;
  orgForm.is_active = org.is_active;
};

const loadMembers = async () => {
  if (!selectedOrgId.value || !canReadMembers.value) {
    members.value = [];
    return;
  }
  members.value = await organizationsApi.listOrganizationMembers(selectedOrgId.value);
};

const onSelectTree = (keys: (string | number)[]) => {
  if (keys.length) selectedKey.value = String(keys[0]);
};

watch(selectedOrg, (org) => {
  syncOrgForm(org);
  detailTab.value = "info";
  void loadMembers();
});

watch(
  organizations,
  (list) => {
    if (selectedOrgId.value && !list.some((o) => o.id === selectedOrgId.value)) {
      selectedKey.value = "platform";
    }
  },
  { deep: true },
);

const saveOrg = () => {
  if (!selectedOrgId.value) return;
  const name = orgForm.name.trim();
  if (!name) {
    Message.warning("请输入部门名称");
    return;
  }
  void store.wrap(async () => {
    await organizationsApi.updateOrganization(selectedOrgId.value!, {
      name,
      description: orgForm.description.trim() || null,
      max_projects: orgForm.max_projects,
      monthly_ai_token_quota: orgForm.monthly_ai_token_quota,
      is_active: orgForm.is_active,
    });
    await load();
    Message.success("部门信息已保存");
  });
};

const openCreate = () => {
  createForm.name = "";
  createForm.slug = "";
  createForm.description = "";
  createForm.max_projects = 100;
  createForm.monthly_ai_token_quota = 500_000;
  createVisible.value = true;
};

const isDuplicateSlugError = (message: string) =>
  message.includes("部门编码已存在") || /slug already exists/i.test(message);

const focusExistingOrganization = (slug: string) => {
  const existing = organizations.value.find((org) => org.slug === slug);
  if (!existing) return false;
  createVisible.value = false;
  selectedKey.value = `org-${existing.id}`;
  expandedKeys.value = ["platform"];
  Message.warning(`部门编码「${slug}」已存在，已定位到该部门`);
  return true;
};

const createOrg = () => {
  const name = createForm.name.trim();
  const slug = createForm.slug.trim().toLowerCase();
  if (!name) {
    Message.warning("请输入部门名称");
    return;
  }
  if (slug.length < 2) {
    Message.warning("部门编码至少 2 位");
    return;
  }
  void (async () => {
    store.loading.value = true;
    try {
      const org = await organizationsApi.createOrganization({
        name,
        slug,
        description: createForm.description.trim() || null,
        max_projects: createForm.max_projects,
        monthly_ai_token_quota: createForm.monthly_ai_token_quota,
      });
      createVisible.value = false;
      upsertOrganization(org);
      selectedKey.value = `org-${org.id}`;
      expandedKeys.value = ["platform"];
      try {
        await refreshOrganizations();
      } catch {
        // Keep optimistic tree entry when background refresh fails.
      }
      Message.success("部门创建成功");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (isDuplicateSlugError(message)) {
        try {
          await refreshOrganizations();
        } catch {
          // Ignore refresh errors; duplicate guidance still applies.
        }
        if (focusExistingOrganization(slug)) {
          return;
        }
      }
      Message.error(message || "部门创建失败，请稍后重试");
    } finally {
      store.loading.value = false;
    }
  })();
};

const resetMemberForm = () => {
  memberForm.user_id = undefined;
  memberForm.role_names = defaultRoleNames();
};

const resetCreateUserForm = () => {
  createUserForm.username = "";
  createUserForm.display_name = "";
  createUserForm.email = "";
  createUserForm.password = "";
  createUserForm.is_active = true;
  createUserForm.role_names = defaultRoleNames();
};

const openAddUser = () => {
  addUserMode.value = canManageMembers.value ? "existing" : "create";
  resetMemberForm();
  resetCreateUserForm();
  addUserVisible.value = true;
};

const roleIdsFromNames = (names: string[]) =>
  roles.value.filter((r) => names.includes(r.name)).map((r) => r.id);

const addExistingUser = async () => {
  if (!memberForm.user_id) {
    Message.warning("请选择用户");
    return;
  }
  if (!memberForm.role_names.length) {
    Message.warning("请至少选择一个角色");
    return;
  }
  if (selectedKey.value === "platform") {
    if (!canCreateUser.value) {
      Message.warning("需要 user.manage 权限");
      return;
    }
    await rbacApi.updateUser(memberForm.user_id, {
      organization_id: null,
      role_ids: roleIdsFromNames(memberForm.role_names),
    });
    return;
  }
  if (!selectedOrgId.value) return;
  if (!canManageMembers.value) {
    Message.warning("需要 org.member.manage 权限");
    return;
  }
  await organizationsApi.addOrganizationMemberByRoles(selectedOrgId.value, {
    user_id: memberForm.user_id,
    role_names: memberForm.role_names,
  });
};

const createDeptUser = async () => {
  const username = createUserForm.username.trim();
  const password = createUserForm.password;
  if (!username) {
    Message.warning("请输入用户名");
    return;
  }
  if (password.length < 8) {
    Message.warning("密码至少 8 位");
    return;
  }
  if (!createUserForm.role_names.length) {
    Message.warning("请至少选择一个角色");
    return;
  }
  if (!canCreateUser.value) {
    Message.warning("需要 user.manage 权限");
    return;
  }
  const created = await rbacApi.createUser({
    username,
    display_name: createUserForm.display_name.trim() || null,
    email: createUserForm.email.trim() || null,
    password,
    is_active: createUserForm.is_active,
    organization_id: selectedKey.value === "platform" ? null : selectedOrgId.value ?? null,
    role_names: selectedKey.value === "platform" ? [] : createUserForm.role_names,
  });
  if (selectedKey.value === "platform" && createUserForm.role_names.length) {
    await rbacApi.updateUser(created.id, {
      role_ids: roleIdsFromNames(createUserForm.role_names),
    });
  }
};

const submitAddUser = () => {
  void store.wrap(async () => {
    if (addUserMode.value === "existing") {
      await addExistingUser();
    } else {
      await createDeptUser();
    }
    addUserVisible.value = false;
    await load();
    await loadMembers();
    Message.success("用户已添加");
  });
};
</script>

<template>
  <div class="rbac-split-layout">
    <a-card :bordered="false" class="rbac-split-left ai-panel">
      <div class="rbac-split-toolbar">
        <a-button v-if="canManageOrg" type="primary" size="small" @click="openCreate">
          <template #icon><icon-plus /></template>
          新增部门
        </a-button>
        <a-button size="small" @click="load">
          <template #icon><icon-refresh /></template>
        </a-button>
      </div>
      <a-tree
        :key="treeRenderKey"
        :data="treeData"
        v-model:expanded-keys="expandedKeys"
        :selected-keys="[selectedKey]"
        block-node
        @select="onSelectTree"
      />
    </a-card>

    <a-card :bordered="false" class="rbac-split-right ai-panel">
      <template v-if="selectedKey === 'platform'">
        <a-tabs v-model:active-key="detailTab">
          <a-tab-pane key="info" title="基本信息">
            <a-descriptions :column="1" bordered size="medium">
              <a-descriptions-item label="部门名称">平台</a-descriptions-item>
              <a-descriptions-item label="说明">未绑定租户的平台直属用户</a-descriptions-item>
              <a-descriptions-item label="用户数">{{ platformUsers.length }} 人</a-descriptions-item>
            </a-descriptions>
          </a-tab-pane>
          <a-tab-pane key="users" title="用户列表">
            <div v-if="canAddUserHere" class="dept-users-toolbar">
              <a-button type="primary" size="small" @click="openAddUser">
                <template #icon><icon-plus /></template>
                添加用户
              </a-button>
            </div>
            <a-table
              :columns="platformUserColumns"
              :data="platformUsers"
              row-key="id"
              :pagination="tablePagination"
            >
              <template #active="{ record }">
                <a-tag :color="record.is_active ? 'green' : 'gray'" size="small">
                  {{ record.is_active ? "启用" : "停用" }}
                </a-tag>
              </template>
            </a-table>
          </a-tab-pane>
        </a-tabs>
      </template>

      <template v-else-if="selectedOrg">
        <a-tabs v-model:active-key="detailTab">
          <a-tab-pane key="info" title="基本信息">
            <a-form layout="vertical" class="dept-form">
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="部门名称" required>
                    <a-input v-model="orgForm.name" :disabled="!canManageOrg" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="部门编码" required>
                    <a-input v-model="orgForm.slug" disabled />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="项目配额">
                    <a-input-number v-model="orgForm.max_projects" :min="0" :disabled="!canManageOrg" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="AI Token 月配额">
                    <a-input-number
                      v-model="orgForm.monthly_ai_token_quota"
                      :min="0"
                      :disabled="!canManageOrg"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="24">
                  <a-form-item label="备注">
                    <a-textarea v-model="orgForm.description" :disabled="!canManageOrg" :auto-size="{ minRows: 3 }" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="状态" required>
                    <a-radio-group v-model="orgForm.is_active" :disabled="!canManageOrg">
                      <a-radio :value="true">正常</a-radio>
                      <a-radio :value="false">停用</a-radio>
                    </a-radio-group>
                  </a-form-item>
                </a-col>
              </a-row>
              <a-button v-if="canManageOrg" type="primary" :loading="store.loading.value" @click="saveOrg">
                保存
              </a-button>
            </a-form>
          </a-tab-pane>
          <a-tab-pane key="users" title="用户列表">
            <div v-if="canAddUserHere && canReadMembers" class="dept-users-toolbar">
              <a-button type="primary" size="small" @click="openAddUser">
                <template #icon><icon-plus /></template>
                添加用户
              </a-button>
            </div>
            <a-table
              v-if="canReadMembers"
              :columns="memberColumns"
              :data="members"
              row-key="id"
              :pagination="tablePagination"
            >
              <template #roles="{ record }">
                {{ record.role_names?.join("、") || "—" }}
              </template>
              <template #active="{ record }">
                <a-tag :color="record.is_active ? 'green' : 'gray'" size="small">
                  {{ record.is_active ? "启用" : "停用" }}
                </a-tag>
              </template>
            </a-table>
            <a-empty v-else description="需要 org.member.read 权限" />
          </a-tab-pane>
        </a-tabs>
      </template>
    </a-card>
  </div>

  <a-modal v-model:visible="createVisible" title="新增部门" :width="520" unmount-on-close>
    <a-form layout="vertical">
      <a-form-item label="部门名称" required>
        <a-input v-model="createForm.name" placeholder="租户/部门名称" allow-clear />
      </a-form-item>
      <a-form-item label="部门编码" required>
        <a-input v-model="createForm.slug" placeholder="英文标识，如 acme" allow-clear />
      </a-form-item>
      <a-form-item label="备注">
        <a-textarea v-model="createForm.description" :auto-size="{ minRows: 2 }" />
      </a-form-item>
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="项目配额">
            <a-input-number v-model="createForm.max_projects" :min="0" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="AI Token 月配额">
            <a-input-number v-model="createForm.monthly_ai_token_quota" :min="0" />
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>
    <template #footer>
      <div class="modal-footer-actions">
        <a-space>
          <a-button @click="createVisible = false">取消</a-button>
          <a-button type="primary" :loading="store.loading.value" @click="createOrg">确定</a-button>
        </a-space>
      </div>
    </template>
  </a-modal>

  <a-modal
    v-model:visible="addUserVisible"
    :title="selectedKey === 'platform' ? '添加平台用户' : `添加用户到 ${selectedOrg?.name ?? '部门'}`"
    :width="560"
    unmount-on-close
  >
    <a-radio-group v-if="canManageMembers && canCreateUser" v-model="addUserMode" type="button" class="add-user-mode">
      <a-radio value="existing">选择已有用户</a-radio>
      <a-radio value="create">新建用户</a-radio>
    </a-radio-group>

    <a-form v-if="addUserMode === 'existing' && canManageMembers" layout="vertical" class="add-user-form">
      <a-form-item label="用户" required>
        <a-select
          v-model="memberForm.user_id"
          placeholder="搜索并选择用户"
          allow-search
          allow-clear
          class="dept-field-full"
        >
          <a-option v-for="u in bindableUsers" :key="u.id" :value="u.id">
            {{ u.username }}
            <span v-if="u.display_name" class="text-muted"> · {{ u.display_name }}</span>
          </a-option>
        </a-select>
        <div v-if="!bindableUsers.length" class="text-muted add-user-hint">暂无可添加的用户</div>
      </a-form-item>
      <a-form-item label="用户角色" required>
        <a-select
          v-model="memberForm.role_names"
          multiple
          allow-search
          placeholder="选择角色"
          class="dept-field-full"
          :options="roleOptions"
        />
      </a-form-item>
    </a-form>

    <a-form v-else-if="canCreateUser" layout="vertical" class="add-user-form">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="用户名" required>
            <a-input v-model="createUserForm.username" placeholder="登录用户名" allow-clear />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="昵称">
            <a-input v-model="createUserForm.display_name" placeholder="显示名称" allow-clear />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="邮箱">
            <a-input v-model="createUserForm.email" placeholder="user@example.com" allow-clear />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="密码" required>
            <a-input-password v-model="createUserForm.password" placeholder="至少 8 位" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="用户角色" required>
            <a-select
              v-model="createUserForm.role_names"
              multiple
              allow-search
              placeholder="选择角色"
              class="dept-field-full"
              :options="roleOptions"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="状态">
            <a-radio-group v-model="createUserForm.is_active">
              <a-radio :value="true">启用</a-radio>
              <a-radio :value="false">停用</a-radio>
            </a-radio-group>
          </a-form-item>
        </a-col>
      </a-row>
      <p v-if="selectedKey !== 'platform'" class="text-muted add-user-hint">
        新建用户将自动归属当前部门：{{ selectedOrg?.name }}
      </p>
    </a-form>

    <a-empty v-else description="无权添加用户" />

    <template #footer>
      <div class="modal-footer-actions">
        <a-space>
          <a-button @click="addUserVisible = false">取消</a-button>
          <a-button type="primary" :loading="store.loading.value" @click="submitAddUser">确定</a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.dept-users-toolbar {
  margin-bottom: 12px;
}

.add-user-mode {
  margin-bottom: 16px;
}

.add-user-form {
  margin-top: 4px;
}

.add-user-hint {
  margin: 0;
  font-size: 12px;
}

.dept-field-full,
:deep(.dept-field-full) {
  width: 100%;
}

.text-muted {
  color: var(--color-text-3);
}
</style>
