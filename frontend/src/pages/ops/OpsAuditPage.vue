<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { onMounted, ref } from "vue";
import { adminApi } from "../../api/admin";
import { downloadBlob } from "../../api/client";
import { listTablePagination } from "../../constants/listPagination";
import { usePlatformStore } from "../../state/platform";
import type { AuditLog } from "../../types";

const store = usePlatformStore();
const logs = ref<AuditLog[]>([]);
const moduleFilter = ref("");
const actionFilter = ref("");
const levelFilter = ref("");
const purgeDays = ref(180);

const columns = [
  { title: "ID", dataIndex: "id", width: 70 },
  { title: "模块", dataIndex: "module", width: 110 },
  { title: "动作", dataIndex: "action", width: 150 },
  { title: "级别", dataIndex: "level", width: 80 },
  { title: "消息", dataIndex: "message", ellipsis: true },
  { title: "时间", dataIndex: "created_at", width: 180 },
];

const tablePagination = listTablePagination(10);

const load = () =>
  store.wrap(async () => {
    logs.value = await adminApi.listLogs({
      module: moduleFilter.value || undefined,
      action: actionFilter.value || undefined,
      level: levelFilter.value || undefined,
    });
    store.setOut(logs.value);
  });

const exportCsv = () => {
  if (!store.hasPermission("audit.export")) {
    Message.warning("缺少 audit.export 权限");
    return;
  }
  void store.wrap(async () => {
    const q = new URLSearchParams();
    if (moduleFilter.value) q.set("module", moduleFilter.value);
    q.set("days", "90");
    await downloadBlob(`/logs/export?${q.toString()}`, `audit-logs-${Date.now()}.csv`);
    Message.success("已导出 CSV");
  });
};

const purge = () => {
  if (!store.hasPermission("audit.manage")) {
    Message.warning("缺少 audit.manage 权限");
    return;
  }
  Modal.confirm({
    title: "确认清理过期审计日志？",
    content: `将删除 ${purgeDays.value} 天以前的审计记录（不可恢复）。近期日志不受影响。`,
    onOk: () =>
      store.wrap(async () => {
        const result = await adminApi.purgeLogs(purgeDays.value);
        Message.success(`已清理 ${result.deleted} 条`);
        await load();
      }),
  });
};

onMounted(() => {
  void load();
});
</script>

<template>
  <div>
    <a-alert
      type="info"
      show-icon
      style="margin-bottom: 16px"
      title="审计日志只读查询为主；导出/留存清理需独立权限。禁止在界面篡改审计内容。"
    />
    <a-card title="审计查询" class="ai-panel">
      <a-space wrap style="margin-bottom: 12px">
        <a-input v-model="moduleFilter" placeholder="模块" style="width: 120px" allow-clear />
        <a-input v-model="actionFilter" placeholder="动作包含" style="width: 140px" allow-clear />
        <a-select v-model="levelFilter" placeholder="级别" allow-clear style="width: 110px">
          <a-option value="info">info</a-option>
          <a-option value="warning">warning</a-option>
          <a-option value="error">error</a-option>
        </a-select>
        <a-button type="primary" class="ai-action-btn" @click="load">查询</a-button>
        <a-button :disabled="!store.hasPermission('audit.export')" @click="exportCsv">导出 CSV</a-button>
        <a-input-number v-model="purgeDays" :min="30" :max="3650" />
        <a-button status="warning" :disabled="!store.hasPermission('audit.manage')" @click="purge">
          清理过期
        </a-button>
      </a-space>
      <a-table :data="logs" :columns="columns" row-key="id" :pagination="tablePagination" />
    </a-card>
  </div>
</template>
