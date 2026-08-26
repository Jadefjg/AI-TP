<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { dashboardApi } from "../api/dashboard";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import K6LineChart from "../components/K6LineChart.vue";
import RunHealthChart from "../components/RunHealthChart.vue";
import RunTrendChart from "../components/RunTrendChart.vue";
import {
  AI_PIPELINE_STEPS,
  buildPipelineQuery,
  recalledPipelineProjectId,
} from "../constants/aiPipeline";
import { usePlatformStore } from "../state/platform";
import type { AiUsageSummary, DashboardRunTrends, DashboardSummary, SystemOverview } from "../types";

const store = usePlatformStore();
const router = useRouter();
const summary = ref<DashboardSummary | null>(null);
const runTrends = ref<DashboardRunTrends | null>(null);
const systemOverview = ref<SystemOverview | null>(null);
const aiUsage = ref<AiUsageSummary | null>(null);
const trendDays = ref(7);
const pageLoading = ref(false);
const trendsLoading = ref(false);

const moduleColumns = [
  { title: "模块", dataIndex: "module" },
  { title: "调用次数", dataIndex: "count" },
];

const moduleTableData = computed(() =>
  Object.entries(aiUsage.value?.by_module || {}).map(([module, count]) => ({ module, count })),
);

const completedRunCount = computed(() => {
  const total = summary.value?.total_run_count ?? 0;
  const failed = summary.value?.failed_run_count ?? 0;
  const running = summary.value?.running_run_count ?? 0;
  const pending = summary.value?.pending_run_count ?? 0;
  return Math.max(0, total - failed - running - pending);
});

const statCards = computed(() => [
  { title: "项目数", value: summary.value?.project_count ?? 0 },
  { title: "用例数", value: summary.value?.case_count ?? 0 },
  { title: "失败任务", value: summary.value?.failed_run_count ?? 0, color: "red" },
  { title: "功能用例项", value: summary.value?.functional_run_count ?? 0 },
  { title: "自动化项", value: summary.value?.automation_run_count ?? 0 },
  { title: "AI Tokens", value: summary.value?.ai_token_total ?? 0 },
]);

const k6Series = computed(() => summary.value?.latest_k6?.time_series || []);
const k6Subtitle = computed(() => {
  const k6 = summary.value?.latest_k6;
  if (!k6) return "";
  return `${k6.project_name || "项目"} · job #${k6.job_id} · ${k6.time_series_source}`;
});

const goPipeline = (routeName: string) => {
  void router.push({
    name: routeName,
    query: buildPipelineQuery({ projectId: recalledPipelineProjectId() }),
  });
};

const loadTrends = () =>
  store.runBackground(async () => {
    trendsLoading.value = true;
    try {
      runTrends.value = await dashboardApi.getDashboardRunTrends(trendDays.value);
    } finally {
      trendsLoading.value = false;
    }
  });

const load = () => {
  pageLoading.value = true;
  return store
    .wrap(async () => {
      const data = await dashboardApi.getDashboardOverview(trendDays.value);
      summary.value = data.summary;
      runTrends.value = data.run_trends;
      systemOverview.value = data.system_overview;
      aiUsage.value = data.ai_usage;
      store.setOut({ dashboard: summary.value, aiUsage: aiUsage.value });
    })
    .finally(() => {
      pageLoading.value = false;
    });
};

watch(trendDays, () => {
  void loadTrends();
});

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="ai-workspace">
    <AiWorkspaceHero
      title="监控大盘"
      subtitle="Run 健康度、AI 用量与全链路质量脉搏 — 从首页一键进入智能流水"
      badge="AI · COMMAND"
      :status-label="pageLoading ? '同步中' : '系统在线'"
      :status-tone="pageLoading ? 'busy' : 'online'"
    >
      <template #extra>
        <a-button type="primary" class="ai-action-btn" :loading="pageLoading" @click="load">
          刷新洞察
        </a-button>
      </template>
    </AiWorkspaceHero>

    <a-card class="ai-panel ai-launch-panel" title="智能流水入口" style="margin-bottom: 16px">
      <a-typography-text type="secondary">
        建议按顺序推进：需求 Agent → UI Agent → 接口 Agent → 性能 Agent → 安全 Agent。顶栏可切换当前项目，上下文会带到各阶段。
      </a-typography-text>
      <div class="ai-launch" style="margin-top: 14px">
        <button
          v-for="step in AI_PIPELINE_STEPS"
          :key="step.key"
          type="button"
          class="ai-launch__card"
          @click="goPipeline(step.routeName)"
        >
          <span class="ai-launch__no">{{ step.short }}</span>
          <span class="ai-launch__label">{{ step.label }}</span>
          <span class="ai-launch__hint">{{ step.hint }}</span>
        </button>
      </div>
    </a-card>

    <div class="dash-ai-banner">
      <div>
        <div class="dash-ai-banner__badge">AI USAGE PULSE</div>
        <div class="dash-ai-banner__title">智能流水实时概览</div>
        <div class="dash-ai-banner__desc">
          从需求 Agent 到安全 Agent（含 Playwright GUI Agent），Agent 调用量与 Run 健康度一目了然。
        </div>
      </div>
      <div class="dash-ai-banner__stat">
        <div class="dash-ai-banner__value">{{ summary?.ai_token_total ?? 0 }}</div>
        <div class="dash-ai-banner__label">累计 AI Tokens</div>
      </div>
    </div>

    <a-row :gutter="16" class="stat-row">
      <a-col v-for="card in statCards" :key="card.title" :xs="24" :sm="12" :md="8" :lg="6">
        <a-card class="ai-panel">
          <a-statistic
            :title="card.title"
            :value="card.value"
            :value-style="card.color ? { color: 'rgb(var(--red-6))' } : undefined"
          />
        </a-card>
      </a-col>
    </a-row>

    <a-card class="ai-panel" title="Run 趋势（近 N 天）" style="margin-top: 16px">
      <template #extra>
        <a-select v-model="trendDays" style="width: 100px" :loading="trendsLoading">
          <a-option :value="7">7 天</a-option>
          <a-option :value="14">14 天</a-option>
          <a-option :value="30">30 天</a-option>
        </a-select>
      </template>
      <a-empty v-if="!runTrends?.points?.length" description="暂无 Run 历史数据" />
      <RunTrendChart v-else :points="runTrends.points" :days="runTrends.days" />
    </a-card>

    <a-row :gutter="16" style="margin-top: 16px">
      <a-col :xs="24" :md="12">
        <a-card class="ai-panel" title="Run 健康度（当前快照）">
          <RunHealthChart
            :failed="summary?.failed_run_count ?? 0"
            :running="summary?.running_run_count ?? 0"
            :pending="summary?.pending_run_count ?? 0"
            :completed="completedRunCount"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-card v-if="systemOverview" class="ai-panel" title="系统信息">
          <a-descriptions :column="1" size="medium">
            <a-descriptions-item label="API">
              {{ systemOverview.api_name }} {{ systemOverview.api_version }}
            </a-descriptions-item>
            <a-descriptions-item label="用户">{{ systemOverview.user_count }}</a-descriptions-item>
            <a-descriptions-item label="总 Run">{{ summary?.total_run_count ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="最近状态">{{ summary?.latest_run_status || "-" }}</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>
    </a-row>

    <a-card class="ai-panel" title="k6 性能时序（ECharts）" style="margin-top: 16px">
      <a-empty v-if="!k6Series.length" description="暂无 k6 时序数据，执行 perf k6 后刷新" />
      <K6LineChart v-else :series="k6Series" :subtitle="k6Subtitle" />
    </a-card>

    <a-card v-if="aiUsage" class="ai-panel" title="AI 模块调用分布" style="margin-top: 16px">
      <a-table :columns="moduleColumns" :data="moduleTableData" :pagination="false" row-key="module" />
    </a-card>
  </div>
</template>

<style scoped>
.stat-row .arco-card {
  margin-bottom: 16px;
}

.dash-ai-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 18px 20px;
  border-radius: 16px;
  border: 1px solid rgba(14, 165, 233, 0.28);
  background: linear-gradient(120deg, rgba(14, 165, 233, 0.12), rgba(34, 211, 238, 0.08));
  box-shadow: 0 10px 28px rgba(14, 165, 233, 0.08);
}

.dash-ai-banner__badge {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0369a1;
}

.dash-ai-banner__title {
  margin-top: 4px;
  font-size: 16px;
  font-weight: 700;
}

.dash-ai-banner__desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-2);
}

.dash-ai-banner__stat {
  text-align: right;
  flex-shrink: 0;
}

.dash-ai-banner__value {
  font-size: 28px;
  font-weight: 760;
  background: linear-gradient(135deg, #0284c7, #0ea5e9);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.dash-ai-banner__label {
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-text-3);
}

@media (max-width: 720px) {
  .dash-ai-banner {
    flex-direction: column;
    align-items: flex-start;
  }

  .dash-ai-banner__stat {
    text-align: left;
  }
}
</style>
