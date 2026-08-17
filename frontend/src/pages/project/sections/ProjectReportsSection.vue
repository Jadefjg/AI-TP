<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { runsApi } from "../../../api/runs";
import { casesApi } from "../../../api/cases";
import { aiApi } from "../../../api/ai";
import { useProjectScope } from "../../../composables/useProjectScope";
import { useRunPoll } from "../../../composables/useRunPoll";
import { usePlatformStore } from "../../../state/platform";
import { DEFAULT_BASE_URL, DEFAULT_HEALTH_URL } from "../../../constants/platformDefaults";
import { resolveProjectBaseUrl, resolveProjectHealthUrl } from "../../../constants/projectDefaults";
import { projectsApi } from "../../../api/projects";
import type { ApiRegressionSet, ReportEmailResult, Run, TestPlan, TestSuite } from "../../../types";
import "../../../assets/project-section.css";

const route = useRoute();
const router = useRouter();
const store = usePlatformStore();
const { projectId } = useProjectScope();

const currentRun = ref<Run | null>(null);
const runs = ref<Run[]>([]);
const testPlans = ref<TestPlan[]>([]);
const testSuites = ref<TestSuite[]>([]);
const apiRegressionSets = ref<ApiRegressionSet[]>([]);
const reportPreview = ref("");
const lastEmail = ref<ReportEmailResult | null>(null);
const reportBusy = ref(false);

const aiForm = reactive({
  baseUrl: DEFAULT_BASE_URL,
  targetUrl: DEFAULT_HEALTH_URL,
  perfDistributed: false,
  securityEngine: "builtin",
});

const runForm = reactive({
  runId: "",
  suiteId: "",
  planId: "",
  kinds: ["unit", "api"] as string[],
  apiMode: "auto",
  apiBaseUrl: DEFAULT_BASE_URL,
  regressionSetId: "",
  perfMode: "auto",
  perfBaseUrl: DEFAULT_BASE_URL,
  securityMode: "combined",
  securityEngine: "builtin",
});

watch(
  projectId,
  (id) => {
    if (!id) return;
    void store.runBackground(async () => {
      try {
        const project = await projectsApi.getProject(id);
        const base = resolveProjectBaseUrl(project);
        aiForm.baseUrl = base;
        aiForm.targetUrl = resolveProjectHealthUrl(project);
        runForm.apiBaseUrl = base;
        runForm.perfBaseUrl = base;
      } catch {
        /* keep defaults */
      }
    });
  },
  { immediate: true },
);

const allKinds = [
  { value: "unit", label: "单元测试" },
  { value: "functional", label: "功能用例（套件/计划）" },
  { value: "api", label: "接口自动化" },
  { value: "ui", label: "UI 自动化" },
  { value: "perf_backend", label: "后端性能" },
  { value: "perf_frontend", label: "前端性能" },
  { value: "sec_backend", label: "后端安全" },
  { value: "sec_frontend", label: "前端安全" },
];

const hasRuns = computed(() => store.hasPermission("run.read"));
const hasRunExecute = computed(() => store.hasPermission("run.execute"));
const hasReportRead = computed(() => store.hasPermission("report.read"));
const hasReportSend = computed(() => store.hasPermission("report.send"));

const resolvedRunId = computed(() => {
  const n = Number(runForm.runId);
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
});

const ensureRunId = () => {
  if (resolvedRunId.value) return resolvedRunId.value;
  Message.warning("请先填写或选择有效的 Run ID（可从下方最近 Run 选择）");
  return null;
};

const statusLabel = (status: string) => {
  const map: Record<string, string> = {
    completed: "已完成",
    failed: "失败",
    running: "运行中",
    pending: "等待中",
    cancelled: "已取消",
  };
  return map[status] || status;
};

const { start: startRunPoll } = useRunPoll(currentRun, {
  onSettled: () => {
    if (hasRuns.value) void loadRuns();
  },
});

const loadRuns = () =>
  store.wrap(async () => {
    if (!hasRuns.value) return;
    runs.value = await runsApi.listProjectRuns(projectId.value);
    if (!runForm.runId && runs.value.length) {
      runForm.runId = String(runs.value[0].id);
    }
  });

const loadTestOrg = () =>
  store.wrap(async () => {
    testPlans.value = await casesApi.listTestPlans(projectId.value);
    testSuites.value = await casesApi.listTestSuites(projectId.value);
    store.setOut({ testPlans: testPlans.value, testSuites: testSuites.value });
  });

const loadApiRegressionSets = () =>
  store.wrap(async () => {
    apiRegressionSets.value = await aiApi.listApiRegressionSets(projectId.value);
  });

const startRun = () =>
  store.wrap(async () => {
    const regressionId = runForm.regressionSetId ? Number(runForm.regressionSetId) : null;
    const suiteId = runForm.suiteId ? Number(runForm.suiteId) : null;
    const planId = runForm.planId ? Number(runForm.planId) : null;
    const result = await runsApi.startRun(projectId.value, runForm.kinds, {
      suite_id: suiteId && !Number.isNaN(suiteId) ? suiteId : null,
      plan_id: planId && !Number.isNaN(planId) ? planId : null,
      api_mode: runForm.apiMode,
      api_base_url: runForm.apiBaseUrl || aiForm.baseUrl,
      regression_set_id: regressionId && !Number.isNaN(regressionId) ? regressionId : null,
      perf_mode: runForm.perfMode,
      perf_base_url: runForm.perfBaseUrl || aiForm.baseUrl,
      perf_distributed: aiForm.perfDistributed,
      security_mode: runForm.securityMode,
      security_target_url: aiForm.targetUrl,
      security_engine: runForm.securityEngine || aiForm.securityEngine,
    });
    currentRun.value = result;
    runForm.runId = String(result.id);
    store.setOut(result);
    startRunPoll(result.id);
    Message.success(`已启动 Run #${result.id}`);
    if (hasRuns.value) {
      runs.value = await runsApi.listProjectRuns(projectId.value);
    }
  });

const runRegressionClosedLoop = () =>
  store.wrap(async () => {
    const setId = Number(runForm.regressionSetId);
    if (!setId) {
      Message.warning("请选择回归集");
      return;
    }
    const result = await runsApi.startRun(projectId.value, ["api"], {
      api_mode: "dsl",
      api_base_url: runForm.apiBaseUrl || aiForm.baseUrl,
      regression_set_id: setId,
    });
    currentRun.value = result;
    runForm.runId = String(result.id);
    store.setOut(result);
    startRunPoll(result.id);
    Message.success(`回归集闭环 Run #${result.id} 已启动`);
  });

const getRun = () => {
  const id = ensureRunId();
  if (!id) return;
  void store.wrap(async () => {
    const result = await runsApi.getRun(id);
    currentRun.value = result;
    store.setOut(result);
    Message.success(`已加载 Run #${id}（${statusLabel(result.status)}）`);
  });
};

const createReport = () => {
  const id = ensureRunId();
  if (!id) return;
  if (currentRun.value && ["pending", "running"].includes(currentRun.value.status)) {
    Message.warning("Run 仍在执行中，请完成后再生成报告");
    return;
  }
  reportBusy.value = true;
  void store
    .wrap(async () => {
      // Ensure we have latest status
      const run = await runsApi.getRun(id);
      currentRun.value = run;
      if (["pending", "running"].includes(run.status)) {
        Message.warning("Run 仍在执行中，请完成后再生成报告");
        return;
      }
      const result = await runsApi.createReport(id);
      store.setOut(result);
      reportPreview.value = await runsApi.fetchReportHtml(id);
      Message.success(`报告已生成（#${result.id ?? id}）`);
    })
    .finally(() => {
      reportBusy.value = false;
    });
};

const sendReport = () => {
  const id = ensureRunId();
  if (!id) return;
  void store.wrap(async () => {
    const result = await runsApi.sendReport(id);
    lastEmail.value = result;
    store.setOut(result);
    if (result.ok && result.mode === "smtp") {
      Message.success(`报告已发送：${result.sent_to.join(", ")}`);
    } else if (result.mode === "outbox" || result.skipped) {
      Message.warning(result.reason || "未配置 SMTP，仅写入本地发件箱");
    } else {
      Message.warning(result.reason || "邮件未发送");
    }
  });
};

const openRunDetail = () => {
  const id = ensureRunId();
  if (!id) return;
  void router.push({ name: "task-run-detail", params: { runId: String(id) } });
};

const onPickRecentRun = (value: string | number | boolean) => {
  runForm.runId = String(value);
  void getRun();
};

watch(
  () => route.query.runId,
  (runId) => {
    if (!runId) return;
    runForm.runId = String(Array.isArray(runId) ? runId[0] : runId);
    const id = Number(runForm.runId);
    if (!Number.isNaN(id) && id > 0) {
      void getRun();
      startRunPoll(id);
    }
  },
  { immediate: true },
);

onMounted(() => {
  void loadTestOrg();
  void loadApiRegressionSets();
  void loadRuns();
});
</script>

<template>
  <a-card title="执行与报告" class="ai-panel ai-panel--accent">
    <div class="ai-chip-rail">
      <span class="ai-chip ai-chip--live">执行</span>
      <span class="ai-chip">报告</span>
    </div>
    <a-typography-text type="secondary">
      先启动或选择 Run，再点「报告」生成 HTML；「发送」将报告投递给项目收件人（未配 SMTP 时写入本地发件箱）。
    </a-typography-text>

    <a-row :gutter="8" style="margin-top: 12px">
      <a-col :span="8">
        <a-input v-model="runForm.runId" placeholder="Run ID（必填）" allow-clear>
          <template #prefix>Run</template>
        </a-input>
      </a-col>
      <a-col :span="10">
        <a-select
          v-if="runs.length"
          :model-value="runForm.runId || undefined"
          placeholder="从最近 Run 选择"
          allow-search
          @change="onPickRecentRun"
        >
          <a-option v-for="row in runs" :key="row.id" :value="String(row.id)">
            #{{ row.id }} · {{ statusLabel(row.status) }}
          </a-option>
        </a-select>
      </a-col>
      <a-col :span="6">
        <a-button long type="outline" :disabled="!resolvedRunId" @click="openRunDetail">打开详情</a-button>
      </a-col>
    </a-row>

    <a-checkbox-group v-if="hasRunExecute" v-model="runForm.kinds" style="margin: 12px 0">
      <a-checkbox v-for="kind in allKinds" :key="kind.value" :value="kind.value">{{ kind.label }}</a-checkbox>
    </a-checkbox-group>
    <a-row v-if="hasRunExecute" :gutter="8" style="margin-bottom: 8px">
      <a-col :span="8">
        <a-select v-model="runForm.suiteId" placeholder="测试套件（执行全部用例）" allow-clear>
          <a-option v-for="s in testSuites" :key="s.id" :value="String(s.id)">{{ s.name }} (#{{ s.id }})</a-option>
        </a-select>
      </a-col>
      <a-col :span="8">
        <a-select v-model="runForm.planId" placeholder="测试计划（执行计划下全部套件）" allow-clear>
          <a-option v-for="p in testPlans" :key="p.id" :value="String(p.id)">{{ p.name }} (#{{ p.id }})</a-option>
        </a-select>
      </a-col>
      <a-col :span="8">
        <a-typography-text type="secondary">选择套件/计划将自动加入 functional 项执行用例</a-typography-text>
      </a-col>
    </a-row>
    <a-row v-if="hasRunExecute" :gutter="8" style="margin-bottom: 8px">
      <a-col :span="8">
        <a-select v-model="runForm.apiMode" placeholder="api 模式">
          <a-option value="auto">自动（有 DSL 则用 DSL）</a-option>
          <a-option value="dsl">强制 DSL</a-option>
          <a-option value="pytest">传统 pytest</a-option>
        </a-select>
      </a-col>
      <a-col :span="8">
        <a-input v-model="runForm.apiBaseUrl" placeholder="API Base URL" />
      </a-col>
      <a-col :span="8">
        <a-select v-model="runForm.regressionSetId" placeholder="回归集（可选）" allow-clear>
          <a-option v-for="s in apiRegressionSets" :key="s.id" :value="String(s.id)">{{ s.name }} (#{{ s.id }})</a-option>
        </a-select>
      </a-col>
    </a-row>
    <a-row v-if="hasRunExecute" :gutter="8" style="margin-bottom: 8px">
      <a-col :span="8">
        <a-select v-model="runForm.perfMode">
          <a-option value="auto">性能自动（有方案则 k6）</a-option>
          <a-option value="k6">性能 k6</a-option>
          <a-option value="legacy">性能传统</a-option>
        </a-select>
      </a-col>
      <a-col :span="8">
        <a-select v-model="runForm.securityMode">
          <a-option value="combined">安全合并 bandit/audit + AI</a-option>
          <a-option value="auto">安全自动</a-option>
          <a-option value="ai">安全仅 AI</a-option>
          <a-option value="legacy">安全仅传统</a-option>
        </a-select>
      </a-col>
      <a-col :span="8">
        <a-select v-model="runForm.securityEngine">
          <a-option value="builtin">builtin</a-option>
          <a-option value="nuclei">nuclei</a-option>
          <a-option value="zap">zap</a-option>
          <a-option value="combined">combined</a-option>
        </a-select>
      </a-col>
    </a-row>
    <a-space wrap>
      <a-button v-if="hasRunExecute" type="primary" class="ai-action-btn" @click="startRun">启动测试</a-button>
      <a-button v-if="hasRunExecute && runForm.regressionSetId" type="outline" @click="runRegressionClosedLoop">
        回归集闭环 Run
      </a-button>
      <a-button v-if="hasRuns" @click="getRun">查询</a-button>
      <a-button v-if="hasReportRead" type="outline" :loading="reportBusy" @click="createReport">报告</a-button>
      <a-button v-if="hasReportSend" @click="sendReport">发送</a-button>
    </a-space>

    <a-alert v-if="currentRun" type="info" style="margin-top: 12px">
      当前 Run #{{ currentRun.id }} — {{ statusLabel(currentRun.status) }}
    </a-alert>
    <a-alert
      v-if="lastEmail"
      style="margin-top: 8px"
      :type="
        !lastEmail.ok
          ? 'warning'
          : lastEmail.mode === 'outbox' || lastEmail.skipped
            ? 'warning'
            : 'success'
      "
      :title="
        !lastEmail.ok
          ? '邮件未发送'
          : lastEmail.mode === 'outbox' || lastEmail.skipped
            ? '未真实投递（本地发件箱）'
            : '邮件已发送'
      "
      closable
      @close="lastEmail = null"
    >
      <template v-if="lastEmail.ok || lastEmail.mode === 'outbox'">
        收件人：{{ lastEmail.sent_to.join(", ") }}
        <div v-if="lastEmail.reason">{{ lastEmail.reason }}</div>
      </template>
      <template v-else>{{ lastEmail.reason || "发送失败" }}</template>
    </a-alert>

    <a-card v-if="reportPreview" title="报告预览" class="ai-panel" style="margin-top: 16px" size="small">
      <iframe class="report-preview-frame" :srcdoc="reportPreview" title="report preview" />
    </a-card>
  </a-card>
</template>

<style scoped>
.report-preview-frame {
  width: 100%;
  min-height: 420px;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  background: #fff;
}
</style>
