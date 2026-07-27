<script setup lang="ts">
import { onMounted, ref } from "vue";
import { runsApi } from "../../../api/runs";
import { listTablePagination } from "../../../constants/listPagination";
import { useProjectScope } from "../../../composables/useProjectScope";
import { usePlatformStore } from "../../../state/platform";
import type { Run } from "../../../types";
import "../../../assets/project-section.css";

const store = usePlatformStore();
const { projectId } = useProjectScope();
const runs = ref<Run[]>([]);
const tablePagination = listTablePagination(10);

const runColumns = [
  { title: "Run", dataIndex: "id", width: 80 },
  { title: "状态", dataIndex: "status", width: 120 },
  { title: "创建时间", dataIndex: "created_at" },
  { title: "测试项", slotName: "items" },
];

const loadRuns = () =>
  store.wrap(async () => {
    runs.value = await runsApi.listProjectRuns(projectId.value);
    store.setOut({ runs: runs.value });
  });

onMounted(() => {
  void loadRuns();
});
</script>

<template>
  <a-card title="运行结果" class="ai-panel ai-fill-panel">
    <div class="ai-chip-rail">
      <span class="ai-chip ai-chip--live">Runs</span>
      <span class="ai-chip">{{ runs.length }} records</span>
    </div>
    <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" style="margin-bottom: 12px" @click="loadRuns">
      刷新
    </a-button>
    <div v-if="!runs.length" class="ai-empty">
      <p class="ai-empty__title">暂无运行记录</p>
      <p class="ai-empty__desc">在报告页发起 Run，或从智能流水进入任务中心查看执行。</p>
    </div>
    <a-table v-else :columns="runColumns" :data="runs" row-key="id" :pagination="tablePagination">
      <template #items="{ record }">
        <a-space wrap>
          <a-tag v-for="item in record.items" :key="item.id">{{ item.kind }}: {{ item.status }}</a-tag>
        </a-space>
      </template>
    </a-table>
  </a-card>
</template>
