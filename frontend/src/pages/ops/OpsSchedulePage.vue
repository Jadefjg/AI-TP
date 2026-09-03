<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { onMounted, reactive, ref } from "vue";
import { opsApi, type ScheduledJob, type ScheduledJobRun } from "../../api/ops";
import { usePlatformStore } from "../../state/platform";

const store = usePlatformStore();
const jobs = ref<ScheduledJob[]>([]);
const handlers = ref<Array<{ key: string; label: string; description: string }>>([]);
const runs = ref<ScheduledJobRun[]>([]);
const selectedJobId = ref<number | null>(null);
const form = reactive({
  name: "",
  handler_key: "ops.health_snapshot",
  description: "",
  interval_seconds: 900,
  enabled: true,
});

const canWrite = () => store.hasPermission("schedule.write");

const load = () =>
  store.wrap(async () => {
    handlers.value = await opsApi.listHandlers();
    jobs.value = await opsApi.listJobs();
  });

const loadRuns = (jobId: number) =>
  store.wrap(async () => {
    selectedJobId.value = jobId;
    runs.value = await opsApi.listJobRuns(jobId);
  });

const seed = () =>
  store.wrap(async () => {
    await opsApi.seedJobs();
    Message.success("已种子化默认运维任务");
    await load();
  });

const save = () => {
  if (!canWrite()) {
    Message.warning("缺少 schedule.write");
    return;
  }
  void store.wrap(async () => {
    await opsApi.upsertJob({ ...form });
    Message.success("已保存（仅白名单 handler）");
    form.name = "";
    await load();
  });
};

const toggle = (job: ScheduledJob) => {
  if (!canWrite()) return;
  void store.wrap(async () => {
    await opsApi.enableJob(job.id, !job.enabled);
    await load();
  });
};

const runNow = (job: ScheduledJob) => {
  if (!canWrite()) return;
  Modal.confirm({
    title: "确认手动执行？",
    content: `将立即执行白名单任务「${job.name}」（${job.handler_key}）`,
    onOk: () =>
      store.wrap(async () => {
        const result = await opsApi.runJob(job.id);
        Message.success(`执行结束：${result.status}`);
        await load();
        await loadRuns(job.id);
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
      style="margin-bottom: 12px"
      title="安全约束：仅允许执行后端预注册 handler，禁止页面输入 Shell/SQL。"
    />
    <a-space style="margin-bottom: 12px">
      <a-button type="primary" :disabled="!canWrite()" @click="save">保存任务</a-button>
      <a-button :disabled="!canWrite()" @click="seed">种子默认任务</a-button>
      <a-button @click="load">刷新</a-button>
    </a-space>

    <a-form layout="inline" style="margin-bottom: 12px">
      <a-form-item label="名称"><a-input v-model="form.name" style="width: 160px" /></a-form-item>
      <a-form-item label="Handler">
        <a-select v-model="form.handler_key" style="width: 220px">
          <a-option v-for="h in handlers" :key="h.key" :value="h.key">{{ h.label }}</a-option>
        </a-select>
      </a-form-item>
      <a-form-item label="间隔(秒)">
        <a-input-number v-model="form.interval_seconds" :min="60" :max="2592000" />
      </a-form-item>
      <a-form-item label="描述"><a-input v-model="form.description" style="width: 200px" /></a-form-item>
    </a-form>

    <a-table
      :data="jobs"
      row-key="id"
      :pagination="false"
      :columns="[
        { title: '名称', dataIndex: 'name' },
        { title: 'Handler', dataIndex: 'handler_key', width: 180 },
        { title: '间隔', dataIndex: 'interval_seconds', width: 90 },
        { title: '状态', slotName: 'enabled', width: 90 },
        { title: '上次', dataIndex: 'last_status', width: 100 },
        { title: '操作', slotName: 'actions', width: 220 },
      ]"
    >
      <template #enabled="{ record }">
        <a-tag :color="record.enabled ? 'green' : 'gray'">{{ record.enabled ? "启用" : "停用" }}</a-tag>
      </template>
      <template #actions="{ record }">
        <a-space>
          <a-button size="mini" :disabled="!canWrite()" @click="toggle(record)">启停</a-button>
          <a-button size="mini" type="primary" :disabled="!canWrite()" @click="runNow(record)">执行</a-button>
          <a-button size="mini" @click="loadRuns(record.id)">记录</a-button>
        </a-space>
      </template>
    </a-table>

    <a-card v-if="selectedJobId" title="执行记录" size="small" style="margin-top: 12px">
      <a-table
        :data="runs"
        row-key="id"
        :pagination="false"
        :columns="[
          { title: 'ID', dataIndex: 'id', width: 70 },
          { title: '状态', dataIndex: 'status', width: 100 },
          { title: '触发', dataIndex: 'trigger', width: 90 },
          { title: '耗时ms', dataIndex: 'duration_ms', width: 90 },
          { title: '错误', dataIndex: 'error', ellipsis: true },
          { title: '开始', dataIndex: 'started_at', width: 180 },
        ]"
      />
    </a-card>
  </div>
</template>
