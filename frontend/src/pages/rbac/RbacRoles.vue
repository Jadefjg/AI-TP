<script setup lang="ts">
import { IconPlus, IconRefresh } from "@arco-design/web-vue/es/icon";
import { Message } from "@arco-design/web-vue";
import { computed, reactive, ref, watch } from "vue";
import { rbacApi } from "../../api/rbac";
import { listTablePagination } from "../../constants/listPagination";
import { usePlatformStore } from "../../state/platform";
import type { Role } from "../../types";
import { buildPermissionTree, countUsersForRole, usersForRole } from "./rbac-utils";
import { useRbacData } from "./useRbacData";

const store = usePlatformStore();
const tablePagination = listTablePagination(10);
const { users, roles, permissions, load } = useRbacData();

const keyword = ref("");
const selectedRoleId = ref<number | null>(null);
const detailTab = ref("users");
const createVisible = ref(false);
const createForm = reactive({ name: "", description: "" });
const checkedPermKeys = ref<string[]>([]);
const permDirty = ref(false);

const filteredRoles = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  if (!q) return roles.value;
  return roles.value.filter(
    (r) => r.name.toLowerCase().includes(q) || (r.description ?? "").toLowerCase().includes(q),
  );
});

const selectedRole = computed(
  () => roles.value.find((r) => r.id === selectedRoleId.value) ?? null,
);

const roleUsers = computed(() =>
  selectedRoleId.value != null ? usersForRole(users.value, selectedRoleId.value) : [],
);

const permissionTree = computed(() => buildPermissionTree(permissions.value));

const roleColumns = [
  { title: "角色名称", dataIndex: "name", ellipsis: true },
  { title: "用户数", slotName: "userCount", width: 80 },
  { title: "状态", slotName: "status", width: 90 },
];

const roleUserColumns = [
  { title: "用户 ID", dataIndex: "id", width: 90 },
  { title: "用户名", dataIndex: "username", width: 140 },
  { title: "昵称", dataIndex: "display_name" },
  { title: "邮箱", dataIndex: "email", ellipsis: true },
];

const rowSelection = computed(() => ({
  type: "radio" as const,
  selectedRowKeys: selectedRoleId.value != null ? [selectedRoleId.value] : [],
  showCheckedAll: false,
}));

const syncPermChecks = (role: Role | null) => {
  checkedPermKeys.value = role?.permissions?.map((p) => `perm-${p.id}`) ?? [];
  permDirty.value = false;
};

watch(
  roles,
  (list) => {
    if (!list.length) {
      selectedRoleId.value = null;
      return;
    }
    if (selectedRoleId.value == null || !list.some((r) => r.id === selectedRoleId.value)) {
      selectedRoleId.value = list[0].id;
    }
  },
  { immediate: true },
);

watch(selectedRole, (role) => {
  syncPermChecks(role);
});

const onRoleSelect = (keys: (string | number)[]) => {
  selectedRoleId.value = keys.length ? Number(keys[0]) : null;
};

const openCreate = () => {
  createForm.name = "";
  createForm.description = "";
  createVisible.value = true;
};

const createRole = () => {
  const name = createForm.name.trim();
  if (!name) {
    Message.warning("请输入角色名称");
    return;
  }
  void store.wrap(async () => {
    const role = await rbacApi.createRole({ name, description: createForm.description.trim() || null });
    createVisible.value = false;
    await load();
    selectedRoleId.value = role.id;
    Message.success("角色创建成功");
  });
};

const savePermissions = () => {
  if (!selectedRoleId.value) return;
  const permissionIds = checkedPermKeys.value
    .filter((k) => k.startsWith("perm-"))
    .map((k) => Number(k.replace("perm-", "")))
    .filter((id) => Number.isFinite(id));
  void store.wrap(async () => {
    await rbacApi.assignRolePermissions(selectedRoleId.value!, permissionIds);
    permDirty.value = false;
    await load();
    Message.success("权限设置已保存");
  });
};
</script>

<template>
  <div class="rbac-split-layout">
    <a-card :bordered="false" class="rbac-split-left rbac-role-list-card ai-panel">
      <div class="rbac-split-toolbar">
        <span class="rbac-split-title">角色列表</span>
        <a-space>
          <a-input v-model="keyword" placeholder="请输入关键字" allow-clear size="small" style="width: 140px" />
          <a-button type="primary" size="small" @click="openCreate">
            <template #icon><icon-plus /></template>
            新增
          </a-button>
          <a-button size="small" @click="load">
            <template #icon><icon-refresh /></template>
          </a-button>
        </a-space>
      </div>
      <a-table
        :columns="roleColumns"
        :data="filteredRoles"
        row-key="id"
        :pagination="tablePagination"
        size="small"
        :row-selection="rowSelection"
        @selection-change="onRoleSelect"
      >
        <template #userCount="{ record }">
          {{ countUsersForRole(users, record.id) }} 人
        </template>
        <template #status>
          <a-tag color="green" size="small">启用</a-tag>
        </template>
      </a-table>
    </a-card>

    <a-card :bordered="false" class="rbac-split-right ai-panel">
      <template v-if="selectedRole">
        <a-tabs v-model:active-key="detailTab">
          <a-tab-pane key="users" title="用户列表">
            <a-table
              :columns="roleUserColumns"
              :data="roleUsers"
              row-key="id"
              :pagination="tablePagination"
              size="small"
            />
          </a-tab-pane>
          <a-tab-pane key="perms" title="权限设置">
            <a-tree
              v-if="permissionTree.length"
              :data="permissionTree"
              checkable
              v-model:checked-keys="checkedPermKeys"
              default-expand-all
              block-node
              @check="() => (permDirty = true)"
            />
            <a-empty v-else description="暂无权限数据" />
            <div class="rbac-perm-actions">
              <a-button type="primary" :disabled="!permDirty" :loading="store.loading.value" @click="savePermissions">
                保存权限
              </a-button>
            </div>
          </a-tab-pane>
        </a-tabs>
      </template>
      <a-empty v-else description="请选择角色" />
    </a-card>
  </div>

  <a-modal v-model:visible="createVisible" title="新增角色" unmount-on-close>
    <a-form layout="vertical">
      <a-form-item label="角色名称" required>
        <a-input v-model="createForm.name" placeholder="角色名称" allow-clear />
      </a-form-item>
      <a-form-item label="描述">
        <a-input v-model="createForm.description" placeholder="可选" allow-clear />
      </a-form-item>
    </a-form>
    <template #footer>
      <div class="modal-footer-actions">
        <a-space>
          <a-button @click="createVisible = false">取消</a-button>
          <a-button type="primary" :loading="store.loading.value" @click="createRole">确定</a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.rbac-perm-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border-2);
}
</style>
