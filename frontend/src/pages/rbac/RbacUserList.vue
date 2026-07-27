<script setup lang="ts">
import { IconPlus, IconRefresh } from "@arco-design/web-vue/es/icon";
import { Message } from "@arco-design/web-vue";
import { computed, reactive, ref } from "vue";
import { rbacApi } from "../../api/rbac";
import { listTablePagination } from "../../constants/listPagination";
import { usePlatformStore } from "../../state/platform";
import type { User } from "../../types";
import { filterUsers, roleTagColor } from "./rbac-utils";
import { useRbacData } from "./useRbacData";

/** Arco Select 不支持 null 选项值，0 表示平台 */
const PLATFORM_ORG_VALUE = 0;

const toSelectOrgValue = (orgId: number | null | undefined): number =>
  orgId == null ? PLATFORM_ORG_VALUE : orgId;

const fromSelectOrgValue = (value: number | undefined): number | null =>
  value == null || value === PLATFORM_ORG_VALUE ? null : value;

const store = usePlatformStore();
const tablePagination = listTablePagination(10);
const { users, roles, organizations, orgLabel, load } = useRbacData();

const filters = reactive({
  id: "",
  username: "",
  displayName: "",
  keyword: "",
  activeOnly: null as boolean | null,
});
const appliedFilters = reactive({ ...filters });
const createVisible = ref(false);
const selectedRowKeys = ref<number[]>([]);

const editModal = reactive({
  visible: false,
  mode: "single" as "single" | "batch",
  userId: undefined as number | undefined,
  roleIds: [] as number[],
  organizationId: PLATFORM_ORG_VALUE as number,
  isActive: true,
});

const batchFields = reactive({
  changeRoles: false,
  changeOrg: false,
  changeStatus: false,
});

const userForm = reactive({
  username: "",
  display_name: "",
  email: "",
  password: "",
  is_active: true,
  organization_id: undefined as number | undefined,
});

const orgOptions = computed(() =>
  organizations.value.map((o) => ({ value: o.id, label: `${o.name}（${o.slug}）` })),
);

const allRoleOptions = computed(() =>
  roles.value.map((r) => ({ value: r.id, label: r.name })),
);

const filteredUsers = computed(() => filterUsers(users.value, appliedFilters));

const editModalTitle = computed(() =>
  editModal.mode === "batch" ? `批量修改（已选 ${selectedRowKeys.value.length} 人）` : "编辑用户",
);

const userColumns = [
  { title: "用户 ID", dataIndex: "id", width: 90, sortable: { sortDirections: ["ascend", "descend"] } },
  { title: "用户名", dataIndex: "username", width: 140 },
  { title: "昵称", dataIndex: "display_name", width: 140 },
  { title: "邮箱", dataIndex: "email", ellipsis: true },
  { title: "用户角色", slotName: "roles", width: 220 },
  { title: "用户部门", slotName: "org", width: 160 },
  { title: "状态", slotName: "active", width: 90 },
  { title: "操作", slotName: "actions", width: 120, fixed: "right" as const },
];

const rowSelection = computed(() => ({
  type: "checkbox" as const,
  selectedRowKeys: selectedRowKeys.value,
  showCheckedAll: true,
}));

const resetFilters = () => {
  filters.id = "";
  filters.username = "";
  filters.displayName = "";
  filters.keyword = "";
  filters.activeOnly = null;
  Object.assign(appliedFilters, filters);
};

const search = () => {
  Object.assign(appliedFilters, { ...filters });
};

const resetUserForm = () => {
  userForm.username = "";
  userForm.display_name = "";
  userForm.email = "";
  userForm.password = "";
  userForm.is_active = true;
  userForm.organization_id = undefined;
};

const resetBatchFields = () => {
  batchFields.changeRoles = false;
  batchFields.changeOrg = false;
  batchFields.changeStatus = false;
};

const openCreate = () => {
  resetUserForm();
  createVisible.value = true;
};

const openEditModal = (user: User) => {
  editModal.mode = "single";
  editModal.userId = user.id;
  editModal.roleIds = (user.roles ?? []).map((r) => r.id);
  editModal.organizationId = toSelectOrgValue(user.organization_id);
  editModal.isActive = user.is_active;
  resetBatchFields();
  editModal.visible = true;
};

const openBatchModal = () => {
  if (!selectedRowKeys.value.length) {
    Message.warning("请先选择用户");
    return;
  }
  editModal.mode = "batch";
  editModal.userId = undefined;
  editModal.roleIds = [];
  editModal.organizationId = PLATFORM_ORG_VALUE;
  editModal.isActive = true;
  resetBatchFields();
  editModal.visible = true;
};

const onSelectChange = (keys: (string | number)[]) => {
  selectedRowKeys.value = keys.map((k) => Number(k));
};

const createUser = () => {
  const username = userForm.username.trim();
  const password = userForm.password;
  if (!username) {
    Message.warning("请输入用户名");
    return;
  }
  if (password.length < 8) {
    Message.warning("密码至少 8 位");
    return;
  }
  void store.wrap(async () => {
    await rbacApi.createUser({
      username,
      display_name: userForm.display_name.trim() || null,
      email: userForm.email.trim() || null,
      password,
      is_active: userForm.is_active,
      organization_id: userForm.organization_id ?? null,
    });
    createVisible.value = false;
    resetUserForm();
    await load();
    Message.success("用户创建成功");
  });
};

const saveEdit = () => {
  if (editModal.mode === "single") {
    if (!editModal.userId) return;
    void store.wrap(async () => {
      await rbacApi.updateUser(editModal.userId!, {
        role_ids: editModal.roleIds,
        organization_id: fromSelectOrgValue(editModal.organizationId),
        is_active: editModal.isActive,
      });
      editModal.visible = false;
      await load();
      Message.success("用户信息已更新");
    });
    return;
  }

  const updates: {
    organization_id?: number | null;
    is_active?: boolean;
    role_ids?: number[];
  } = {};
  if (batchFields.changeRoles) updates.role_ids = editModal.roleIds;
  if (batchFields.changeOrg) updates.organization_id = fromSelectOrgValue(editModal.organizationId);
  if (batchFields.changeStatus) updates.is_active = editModal.isActive;
  if (!Object.keys(updates).length) {
    Message.warning("请至少勾选一项要修改的内容");
    return;
  }

  void store.wrap(async () => {
    await rbacApi.batchUpdateUsers(selectedRowKeys.value, updates);
    editModal.visible = false;
    selectedRowKeys.value = [];
    await load();
    Message.success("批量修改成功");
  });
};

</script>

<template>
  <a-card :bordered="false" class="rbac-panel-card ai-panel">
    <a-form layout="inline" class="rbac-filter-form">
      <a-form-item label="用户 ID">
        <a-input v-model="filters.id" placeholder="用户 ID" allow-clear style="width: 120px" />
      </a-form-item>
      <a-form-item label="用户名">
        <a-input v-model="filters.username" placeholder="用户名" allow-clear style="width: 140px" />
      </a-form-item>
      <a-form-item label="昵称">
        <a-input v-model="filters.displayName" placeholder="昵称" allow-clear style="width: 140px" />
      </a-form-item>
      <a-form-item label="状态">
        <a-select v-model="filters.activeOnly" placeholder="全部" allow-clear style="width: 110px">
          <a-option :value="true">启用</a-option>
          <a-option :value="false">停用</a-option>
        </a-select>
      </a-form-item>
      <a-form-item>
        <a-space>
          <a-button @click="resetFilters">重置</a-button>
          <a-button type="primary" @click="search">搜索</a-button>
        </a-space>
      </a-form-item>
    </a-form>

    <div class="rbac-table-toolbar">
      <a-input-search
        v-model="filters.keyword"
        placeholder="请输入关键字"
        allow-clear
        style="width: 240px"
        @search="search"
        @press-enter="search"
      />
      <a-space>
        <a-button
          v-if="selectedRowKeys.length"
          type="outline"
          @click="openBatchModal"
        >
          批量修改（{{ selectedRowKeys.length }}）
        </a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon><icon-plus /></template>
          新增
        </a-button>
        <a-button @click="load">
          <template #icon><icon-refresh /></template>
        </a-button>
      </a-space>
    </div>

    <a-table
      :columns="userColumns"
      :data="filteredUsers"
      row-key="id"
      :row-selection="rowSelection"
      :pagination="tablePagination"
      :scroll="{ x: 1180 }"
      @selection-change="onSelectChange"
    >
      <template #roles="{ record }">
        <a-space wrap>
          <a-tag
            v-for="role in record.roles ?? []"
            :key="role.id"
            :color="roleTagColor(role.name)"
            size="small"
          >
            {{ role.name }}
          </a-tag>
          <span v-if="!record.roles?.length" class="text-muted">—</span>
        </a-space>
      </template>
      <template #org="{ record }">
        <a-tag color="orangered" size="small">{{ orgLabel(record.organization_id) }}</a-tag>
      </template>
      <template #active="{ record }">
        <a-tag :color="record.is_active ? 'green' : 'gray'" size="small">
          {{ record.is_active ? "启用" : "停用" }}
        </a-tag>
      </template>
      <template #actions="{ record }">
        <a-button type="text" size="small" @click="openEditModal(record)">
          编辑
        </a-button>
      </template>
    </a-table>
  </a-card>

  <a-modal v-model:visible="createVisible" title="新增用户" :width="560" unmount-on-close>
    <a-form layout="vertical">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="用户名" required>
            <a-input v-model="userForm.username" placeholder="登录用户名" allow-clear />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="昵称">
            <a-input v-model="userForm.display_name" placeholder="显示名称" allow-clear />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="邮箱">
            <a-input v-model="userForm.email" placeholder="user@example.com" allow-clear />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="密码" required>
            <a-input-password v-model="userForm.password" placeholder="至少 8 位" />
          </a-form-item>
        </a-col>
        <a-col v-if="orgOptions.length" :span="12">
          <a-form-item label="所属租户">
            <a-select
              v-model="userForm.organization_id"
              placeholder="平台用户（不选）"
              allow-clear
              allow-search
              :options="orgOptions"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="状态">
            <a-radio-group v-model="userForm.is_active">
              <a-radio :value="true">启用</a-radio>
              <a-radio :value="false">停用</a-radio>
            </a-radio-group>
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>
    <template #footer>
      <div class="modal-footer-actions">
        <a-space>
          <a-button @click="createVisible = false">取消</a-button>
          <a-button type="primary" :loading="store.loading.value" @click="createUser">确定</a-button>
        </a-space>
      </div>
    </template>
  </a-modal>

  <a-modal v-model:visible="editModal.visible" :title="editModalTitle" :width="560" unmount-on-close>
    <a-form layout="vertical">
      <template v-if="editModal.mode === 'single'">
        <a-form-item label="用户角色">
          <a-select
            v-model="editModal.roleIds"
            multiple
            allow-search
            placeholder="选择角色"
            :options="allRoleOptions"
          />
        </a-form-item>
        <a-form-item label="用户部门">
          <a-select
            v-model="editModal.organizationId"
            allow-search
            placeholder="选择部门/租户"
            class="org-select"
          >
            <a-option :value="PLATFORM_ORG_VALUE" label="平台" />
            <a-option
              v-for="org in organizations"
              :key="org.id"
              :value="org.id"
              :label="`${org.name}（${org.slug}）`"
            />
          </a-select>
        </a-form-item>
        <a-form-item label="状态">
          <a-radio-group v-model="editModal.isActive">
            <a-radio :value="true">启用</a-radio>
            <a-radio :value="false">停用</a-radio>
          </a-radio-group>
        </a-form-item>
      </template>

      <template v-else>
        <p class="batch-hint">勾选要批量修改的字段，未勾选的项将保持不变。</p>
        <a-form-item>
          <a-checkbox v-model="batchFields.changeRoles">修改用户角色</a-checkbox>
          <a-select
            v-model="editModal.roleIds"
            class="batch-field"
            multiple
            allow-search
            placeholder="选择角色"
            :options="allRoleOptions"
            :disabled="!batchFields.changeRoles"
          />
        </a-form-item>
        <a-form-item>
          <a-checkbox v-model="batchFields.changeOrg">修改用户部门</a-checkbox>
          <a-select
            v-model="editModal.organizationId"
            class="batch-field org-select"
            allow-search
            placeholder="选择部门/租户"
            :disabled="!batchFields.changeOrg"
          >
            <a-option :value="PLATFORM_ORG_VALUE" label="平台" />
            <a-option
              v-for="org in organizations"
              :key="org.id"
              :value="org.id"
              :label="`${org.name}（${org.slug}）`"
            />
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-checkbox v-model="batchFields.changeStatus">修改状态</a-checkbox>
          <a-radio-group v-model="editModal.isActive" :disabled="!batchFields.changeStatus">
            <a-radio :value="true">启用</a-radio>
            <a-radio :value="false">停用</a-radio>
          </a-radio-group>
        </a-form-item>
      </template>
    </a-form>
    <template #footer>
      <div class="modal-footer-actions">
        <a-space>
          <a-button @click="editModal.visible = false">取消</a-button>
          <a-button type="primary" :loading="store.loading.value" @click="saveEdit">确定</a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.text-muted {
  color: var(--color-text-3);
}

.batch-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--color-text-3);
}

.batch-field {
  width: 100%;
  margin-top: 8px;
}

.org-select,
:deep(.org-select) {
  width: 100%;
}
</style>
