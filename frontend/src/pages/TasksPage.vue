<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { listTablePagination } from "../constants/listPagination";
import { runsApi } from "../api/runs";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { usePlatformStore } from "../state/platform";

const RUN_STATUS_LABELS: Record<string, string> = {
  failed: "失败",
  running: "运行中",
  pending: "等待中",
  completed: "已完成",
  cancelled: "已取消",
  skipped: "已跳过",
  passed: "通过",
};

const runStatusLabel = (status: string) => RUN_STATUS_LABELS[status] || status;

type RunTask = {
  id: number;
  project_id: number;
  project_name: string | null;
  status: string;
  created_at: string;
  completed_at: string | null;
  kinds: string[];
  failed_item_count: number;
};

const store = usePlatformStore();
const router = useRouter();
const tasks = ref<RunTask[]>([]);
const autoRefresh = ref(true);
const pageLoading = ref(false);
const statusFilter = ref("");
const failedFirst = ref(true);
let timer: ReturnType<typeof setInterval> | null = null;

const tablePagination = listTablePagination(10);

const columns = [
  { title: "运行 ID", dataIndex: "id", width: 72, align: "center" as const },
  { title: "项目", slotName: "project", ellipsis: true, tooltip: true, minWidth: 120 },
  { title: "状态", slotName: "status", width: 100, align: "center" as const },
  { title: "测试项", slotName: "kinds", width: 200 },
  { title: "失败项", slotName: "failed", width: 88, align: "center" as const },
  { title: "创建时间", slotName: "createdAt", width: 168 },
  { title: "操作", slotName: "actions", width: 88, align: "center" as const, fixed: "right" as const },
];

const taskCount = computed(() => tasks.value.length);

const statusColor = (status: string) => {
  if (status === "completed") return "green";
  if (status === "failed") return "red";
  if (status === "running") return "arcoblue";
  return "gray";
};

const formatDateTime = (value: string | null | undefined) => {
  if (!value) return "—";
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return value.replace("T", " ").slice(0, 19);
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
};

const projectLabel = (record: RunTask) => record.project_name || `项目 #${record.project_id}`;

const fetchTasks = async () => {
  tasks.value = (await runsApi.listRecentRuns(40, {
    status: statusFilter.value || undefined,
    failed_first: failedFirst.value,
  })) as RunTask[];
};

const load = (background = false) => {
  const run = async () => {
    await fetchTasks();
    if (!background) {
      store.setOut({ tasks: tasks.value });
    }
  };
  if (background) {
    return store.runBackground(run);
  }
  pageLoading.value = true;
  return store.wrap(run).finally(() => {
    pageLoading.value = false;
  });
};

const openRun = (runId: number) => {
  void router.push({ name: "task-run-detail", params: { runId: String(runId) } });
};

const onVisibilityChange = () => {
  if (!document.hidden && autoRefresh.value) {
    void load(true);
  }
};

onMounted(() => {
  void load();
  timer = setInterval(() => {
    if (autoRefresh.value && !document.hidden) {
      void load(true);
    }
  }, 5000);
  document.addEventListener("visibilitychange", onVisibilityChange);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
  document.removeEventListener("visibilitychange", onVisibilityChange);
});
</script>

<template>
  <div class="tasks-page ai-workspace ai-page-fill">
    <AiWorkspaceHero
      title="任务中心"
      subtitle="全平台 Run 脉搏：失败置顶、状态筛选与实时刷新"
      badge="AI · RUNS"
      :status-label="autoRefresh ? '实时同步' : '已暂停'"
      :status-tone="autoRefresh ? 'online' : 'offline'"
    >
      <template #extra>
        <a-button type="primary" class="ai-action-btn" size="medium" :loading="pageLoading" @click="() => load()">
          刷新列表
        </a-button>
      </template>
    </AiWorkspaceHero>

    <a-card class="tasks-toolbar ai-panel" :bordered="false">
      <div class="tasks-toolbar__inner">
        <div class="tasks-toolbar__left">
          <span class="tasks-toolbar__label">状态筛选</span>
          <a-select
            v-model="statusFilter"
            placeholder="全部状态"
            allow-clear
            size="medium"
            class="tasks-toolbar__select"
            @change="() => load()"
          >
            <a-option value="failed">失败</a-option>
            <a-option value="running">运行中</a-option>
            <a-option value="pending">等待中</a-option>
            <a-option value="completed">已完成</a-option>
            <a-option value="cancelled">已取消</a-option>
          </a-select>
          <a-divider direction="vertical" class="tasks-toolbar__divider" />
          <a-switch
            v-model="failedFirst"
            class="tasks-switch"
            checked-text="失败置顶"
            unchecked-text="时间排序"
            @change="() => load()"
          />
          <a-switch
            v-model="autoRefresh"
            class="tasks-switch"
            checked-text="自动刷新"
            unchecked-text="暂停刷新"
          />
        </div>
        <div class="tasks-toolbar__right">
          <span class="tasks-toolbar__count">共 {{ taskCount }} 条</span>
        </div>
      </div>
    </a-card>

    <a-card class="tasks-table-card ai-panel ai-fill-panel" :bordered="false">
      <a-table
        :data="tasks"
        :columns="columns"
        row-key="id"
        size="medium"
        :stripe="true"
        :loading="pageLoading"
        :pagination="tablePagination"
        :scroll="{ x: 900 }"
      >
        <template #project="{ record }">
          <span class="tasks-project">{{ projectLabel(record) }}</span>
        </template>
        <template #status="{ record }">
          <a-tag :color="statusColor(record.status)" size="small">{{ runStatusLabel(record.status) }}</a-tag>
        </template>
        <template #kinds="{ record }">
          <a-space wrap :size="4">
            <a-tag v-for="k in record.kinds" :key="k" size="small" color="arcoblue">{{ k }}</a-tag>
          </a-space>
        </template>
        <template #failed="{ record }">
          <span :class="{ 'tasks-failed-count': record.failed_item_count > 0 }">
            {{ record.failed_item_count }}
          </span>
        </template>
        <template #createdAt="{ record }">
          <span class="tasks-time">{{ formatDateTime(record.created_at) }}</span>
        </template>
        <template #actions="{ record }">
          <a-button type="text" size="small" @click="openRun(record.id)">详情</a-button>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<style scoped>
.tasks-toolbar,
.tasks-table-card {
  margin-bottom: 16px;
}

.tasks-toolbar :deep(.arco-card-body) {
  padding: 14px 16px;
}

.tasks-table-card :deep(.arco-card-body) {
  padding: 0 16px 16px;
}

.tasks-toolbar__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.tasks-toolbar__left,
.tasks-toolbar__right {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 32px;
}

.tasks-toolbar__label {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--color-text-2);
  white-space: nowrap;
}

.tasks-toolbar__select {
  flex: 0 0 140px;
  width: 140px;
  min-width: 140px;
  max-width: 140px;
}

.tasks-toolbar__select :deep(.arco-select) {
  width: 140px;
}

.tasks-toolbar__select :deep(.arco-select-view) {
  width: 140px;
  min-width: 140px;
  max-width: 140px;
  height: 32px;
  box-sizing: border-box;
}

.tasks-toolbar__select :deep(.arco-select-view-value) {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tasks-toolbar__divider {
  height: 20px;
  margin: 0 4px;
  border-color: var(--color-border-2);
}

.tasks-toolbar__left :deep(.tasks-switch.arco-switch) {
  min-width: 88px;
  height: 28px;
  line-height: 28px;
}

.tasks-toolbar__left :deep(.tasks-switch .arco-switch-text-holder) {
  font-size: 12px;
}

.tasks-toolbar__left :deep(.tasks-switch .arco-switch-handle) {
  top: 4px;
  width: 20px;
  height: 20px;
}

.tasks-toolbar__left :deep(.tasks-switch.arco-switch-checked .arco-switch-handle) {
  left: calc(100% - 20px - 4px);
}

.tasks-toolbar__left :deep(.tasks-switch .arco-switch-text) {
  top: 0;
  font-size: 12px;
  line-height: 28px;
}

.tasks-toolbar__left :deep(.tasks-switch:not(.arco-switch-checked) .arco-switch-text) {
  left: 28px;
  color: var(--color-text-2);
}

.tasks-toolbar__left :deep(.tasks-switch.arco-switch-checked .arco-switch-text) {
  left: 8px;
  color: #fff;
}

.tasks-toolbar__right :deep(.arco-btn) {
  height: 32px;
  padding: 0 16px;
}

.tasks-toolbar__count {
  font-size: 13px;
  color: var(--color-text-3);
  white-space: nowrap;
}

.tasks-table-card :deep(.arco-table-th) {
  font-weight: 600;
  background: var(--color-fill-1);
  white-space: nowrap;
}

.tasks-table-card :deep(.arco-table-td) {
  vertical-align: middle;
}

.tasks-table-card :deep(.arco-table-cell) {
  padding: 12px 16px;
}

.tasks-project {
  font-weight: 500;
  color: var(--color-text-1);
}

.tasks-time {
  font-size: 13px;
  color: var(--color-text-2);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.tasks-failed-count {
  display: inline-block;
  min-width: 1.5em;
  font-weight: 600;
  color: rgb(var(--red-6));
}

@media (max-width: 768px) {
  .tasks-toolbar__inner {
    flex-direction: column;
    align-items: stretch;
  }

  .tasks-toolbar__left,
  .tasks-toolbar__right {
    flex-wrap: wrap;
    justify-content: space-between;
  }

  .tasks-toolbar__select {
    flex: 1;
    min-width: 120px;
  }
}
</style>
