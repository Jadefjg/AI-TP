<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { adminApi } from "../api/admin";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { listTablePagination } from "../constants/listPagination";
import { DEFAULT_BASE_URL } from "../constants/platformDefaults";
import { usePlatformStore } from "../state/platform";

const store = usePlatformStore();
const workers = ref<Array<Record<string, unknown>>>([]);
const jobs = ref<Array<Record<string, unknown>>>([]);
const form = reactive({ name: "", endpoint: DEFAULT_BASE_URL, mode: "http", weight: 100 });

const tablePagination = listTablePagination(10);

const load = () =>
  store.wrap(async () => {
    workers.value = await adminApi.listK6Workers();
    jobs.value = await adminApi.listK6DispatchJobs();
    store.setOut({ workers: workers.value, jobs: jobs.value });
  });

const create = () =>
  store.wrap(async () => {
    await adminApi.createK6Worker(form);
    form.name = "";
    await load();
  });

const health = (id: number) =>
  store.wrap(async () => {
    store.setOut(await adminApi.healthCheckK6Worker(id));
    await load();
  });

const seed = () => store.wrap(async () => {
  await adminApi.seedK6Workers();
  await load();
});

onMounted(() => void load());
</script>

<template>
  <div class="ai-workspace">
    <AiWorkspaceHero
      title="k6 节点"
      subtitle="运维管理 · 分布式压测调度，对接本地节点或 HTTP Worker Agent"
      badge="AI · PERF OPS"
      status-label="调度就绪"
      status-tone="online"
    >
      <template #extra>
        <a-space>
          <a-button @click="seed">种子本地节点</a-button>
          <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="load">
            刷新
          </a-button>
        </a-space>
      </template>
    </AiWorkspaceHero>

    <a-card title="注册节点" class="ai-panel" style="margin-bottom: 16px">
      <a-row :gutter="12">
        <a-col :span="6"><a-input v-model="form.name" placeholder="节点名称" /></a-col>
        <a-col :span="10"><a-input v-model="form.endpoint" placeholder="http://host:port" /></a-col>
        <a-col :span="4">
          <a-select v-model="form.mode">
            <a-option value="http">http</a-option>
            <a-option value="local">local</a-option>
          </a-select>
        </a-col>
        <a-col :span="4"><a-input-number v-model="form.weight" :min="1" :max="1000" /></a-col>
      </a-row>
      <a-button type="primary" class="ai-action-btn" style="margin-top: 8px" @click="create">添加节点</a-button>
    </a-card>

    <a-table
      class="ai-panel"
      :columns="[
        { title: 'ID', dataIndex: 'id', width: 70 },
        { title: '名称', dataIndex: 'name' },
        { title: '节点地址', dataIndex: 'endpoint', ellipsis: true },
        { title: '模式', dataIndex: 'mode', width: 80 },
        { title: '权重', dataIndex: 'weight', width: 80 },
        { title: '健康', dataIndex: 'last_health', width: 100 },
        { title: '操作', slotName: 'actions', width: 100 },
      ]"
      :data="workers"
      row-key="id"
      :pagination="tablePagination"
    >
      <template #actions="{ record }">
        <a-button type="text" @click="health(Number(record.id))">探活</a-button>
      </template>
    </a-table>

    <a-card title="最近下发任务" class="ai-panel" style="margin-top: 16px">
      <a-table
        :columns="[
          { title: '任务 ID', dataIndex: 'id', width: 80 },
          { title: '项目', dataIndex: 'project_id', width: 80 },
          { title: '产物', dataIndex: 'artifact_id', width: 80 },
          { title: '状态', dataIndex: 'status', width: 100 },
        ]"
        :data="jobs"
        row-key="id"
        :pagination="tablePagination"
      />
    </a-card>
  </div>
</template>
