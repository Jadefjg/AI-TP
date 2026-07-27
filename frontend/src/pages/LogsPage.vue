<script setup lang="ts">
import { onMounted, ref } from "vue";
import { adminApi } from "../api/admin";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { listTablePagination } from "../constants/listPagination";
import { usePlatformStore } from "../state/platform";
import type { AuditLog } from "../types";

const store = usePlatformStore();
const logs = ref<AuditLog[]>([]);
const moduleFilter = ref("");

const columns = [
  { title: "ID", dataIndex: "id", width: 70 },
  { title: "模块", dataIndex: "module", width: 120 },
  { title: "动作", dataIndex: "action", width: 160 },
  { title: "级别", dataIndex: "level", width: 80 },
  { title: "消息", dataIndex: "message", ellipsis: true },
  { title: "时间", dataIndex: "created_at", width: 180 },
];

const tablePagination = listTablePagination(10);

const load = () =>
  store.wrap(async () => {
    logs.value = await adminApi.listLogs(moduleFilter.value || undefined);
    store.setOut(logs.value);
  });

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="ai-workspace ai-page-fill">
    <AiWorkspaceHero
      title="操作日志"
      subtitle="系统信息 · 项目、用例、运行、报告、RBAC 等关键操作审计轨迹"
      badge="AI · AUDIT"
      :status-label="`共 ${logs.length} 条`"
      status-tone="online"
    >
      <template #extra>
        <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="load">
          刷新
        </a-button>
      </template>
    </AiWorkspaceHero>

    <a-card class="ai-panel ai-fill-panel">
      <a-space style="margin-bottom: 12px">
        <a-input v-model="moduleFilter" placeholder="模块筛选，如 runs / projects" style="width: 260px" />
        <a-button @click="load">查询</a-button>
      </a-space>
      <a-table :data="logs" :columns="columns" row-key="id" :pagination="tablePagination" />
    </a-card>
  </div>
</template>
