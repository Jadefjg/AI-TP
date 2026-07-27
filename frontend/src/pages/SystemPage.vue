<script setup lang="ts">
import { onMounted, ref } from "vue";
import { dashboardApi } from "../api/dashboard";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { usePlatformStore } from "../state/platform";
import type { SystemOverview } from "../types";

const store = usePlatformStore();
const overview = ref<SystemOverview | null>(null);
const health = ref<string>("-");

type StatCard =
  | { title: string; kind: "number"; value: number }
  | { title: string; kind: "text"; value: string };

const statCards = ref<StatCard[]>([]);

const formatHealthStatus = (status: string) => {
  const normalized = status.trim().toLowerCase();
  if (normalized === "ok" || normalized === "healthy") return "正常";
  if (!status) return "未知";
  return status;
};

const load = () =>
  store.wrap(async () => {
    const [healthRes, overviewRes] = await Promise.all([
      dashboardApi.getHealth(),
      dashboardApi.getSystemOverview(),
    ]);
    health.value = healthRes.status;
    overview.value = overviewRes;
    statCards.value = [
      { title: "健康状态", kind: "text", value: formatHealthStatus(healthRes.status) },
      { title: "API 版本", kind: "text", value: overviewRes.api_version || "—" },
      { title: "项目", kind: "number", value: overviewRes.project_count },
      { title: "用户", kind: "number", value: overviewRes.user_count },
      { title: "角色", kind: "number", value: overviewRes.role_count },
      { title: "权限", kind: "number", value: overviewRes.permission_count },
      { title: "日志", kind: "number", value: overviewRes.log_count },
      { title: "配置", kind: "number", value: overviewRes.setting_count },
    ];
    store.setOut({ health: healthRes, overview: overviewRes });
  });

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="ai-workspace">
    <AiWorkspaceHero
      :title="overview?.api_name || '系统信息'"
      subtitle="平台 API 健康、规模与系统脉搏总览"
      badge="AI · SYSTEM"
      :status-label="health === 'ok' || health === 'healthy' ? '系统在线' : String(health)"
      :status-tone="health === 'ok' || health === 'healthy' ? 'online' : 'busy'"
    >
      <template #extra>
        <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="load">
          刷新
        </a-button>
      </template>
    </AiWorkspaceHero>

    <a-row :gutter="16">
      <a-col v-for="card in statCards" :key="card.title" :xs="12" :sm="8" :md="6">
        <a-card class="ai-panel system-stat-card" style="margin-bottom: 16px">
          <a-statistic v-if="card.kind === 'number'" :title="card.title" :value="card.value" />
          <div v-else class="system-stat-text">
            <div class="system-stat-text__title">{{ card.title }}</div>
            <div class="system-stat-text__value">{{ card.value }}</div>
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.system-stat-text__title {
  margin-bottom: 8px;
  color: var(--color-text-2);
  font-size: 14px;
}

.system-stat-text__value {
  color: var(--color-text-1);
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
  word-break: break-word;
}
</style>
