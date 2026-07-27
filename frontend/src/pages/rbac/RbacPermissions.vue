<script setup lang="ts">
import { IconPlus, IconRefresh } from "@arco-design/web-vue/es/icon";
import { Message } from "@arco-design/web-vue";
import { computed, reactive, ref } from "vue";
import { rbacApi } from "../../api/rbac";
import { listTablePagination } from "../../constants/listPagination";
import { usePlatformStore } from "../../state/platform";
import type { Permission } from "../../types";
import { buildPermissionTree, moduleLabel } from "./rbac-utils";
import { useRbacData } from "./useRbacData";

const store = usePlatformStore();
const tablePagination = listTablePagination(10);
const { permissions, load } = useRbacData();

const keyword = ref("");
const createVisible = ref(false);
const createForm = reactive({ code: "", description: "" });

const permissionTree = computed(() => buildPermissionTree(permissions.value));

type PermRow = {
  key: string;
  name: string;
  displayName: string;
  menuType: string;
  sort: number;
  code: string;
  isModule: boolean;
  permission?: Permission;
  children?: PermRow[];
};

const flatRows = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  const rows: PermRow[] = [];

  for (const node of permissionTree.value) {
    const moduleMatch =
      !q ||
      node.title.toLowerCase().includes(q) ||
      node.children?.some((c) => c.code?.toLowerCase().includes(q));
    if (!moduleMatch) continue;

    const children = (node.children ?? []).filter(
      (c) => !q || c.code?.toLowerCase().includes(q) || (c.description ?? "").toLowerCase().includes(q),
    );

    rows.push({
      key: node.key,
      name: node.title,
      displayName: moduleLabel(node.key.replace("module-", "")),
      menuType: "菜单项",
      sort: node.sort,
      code: node.key.replace("module-", ""),
      isModule: true,
      children: children.map((child) => ({
        key: child.key,
        name: child.code ?? child.title,
        displayName: child.description ?? "—",
        menuType: "权限项",
        sort: child.sort,
        code: child.code ?? "",
        isModule: false,
        permission: permissions.value.find((p) => p.id === child.permissionId),
      })),
    });
  }
  return rows;
});

const columns = [
  { title: "规则名称", dataIndex: "name", width: 220 },
  { title: "显示名称", dataIndex: "displayName", width: 180 },
  { title: "菜单类型", slotName: "menuType", width: 110 },
  { title: "排序序号", dataIndex: "sort", width: 100 },
  { title: "权限标识", dataIndex: "code", width: 200 },
];

const menuTypeColor = (type: string) => {
  if (type === "菜单项") return "arcoblue";
  if (type === "权限项") return "gray";
  return "green";
};

const openCreate = () => {
  createForm.code = "";
  createForm.description = "";
  createVisible.value = true;
};

const createPermission = () => {
  const code = createForm.code.trim();
  if (!code) {
    Message.warning("请输入权限编码");
    return;
  }
  void store.wrap(async () => {
    await rbacApi.createPermission({
      code,
      description: createForm.description.trim() || null,
    });
    createVisible.value = false;
    await load();
    Message.success("权限创建成功");
  });
};
</script>

<template>
  <a-card :bordered="false" class="rbac-panel-card ai-panel">
    <div class="rbac-table-toolbar">
      <span class="rbac-split-title">权限管理</span>
      <a-space>
        <a-input-search
          v-model="keyword"
          placeholder="请输入关键字"
          allow-clear
          style="width: 240px"
        />
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
      :columns="columns"
      :data="flatRows"
      row-key="key"
      :pagination="tablePagination"
      :default-expand-all-rows="true"
    >
      <template #menuType="{ record }">
        <a-tag :color="menuTypeColor(record.menuType)" size="small">{{ record.menuType }}</a-tag>
      </template>
    </a-table>
  </a-card>

  <a-modal v-model:visible="createVisible" title="新增权限" unmount-on-close>
    <a-form layout="vertical">
      <a-form-item label="权限编码" required>
        <a-input v-model="createForm.code" placeholder="如 project.read" allow-clear />
      </a-form-item>
      <a-form-item label="显示名称">
        <a-input v-model="createForm.description" placeholder="权限说明" allow-clear />
      </a-form-item>
    </a-form>
    <template #footer>
      <div class="modal-footer-actions">
        <a-space>
          <a-button @click="createVisible = false">取消</a-button>
          <a-button type="primary" :loading="store.loading.value" @click="createPermission">确定</a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>
