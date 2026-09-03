<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import AiWorkspaceHero from "../../components/ai/AiWorkspaceHero.vue";
import { usePlatformStore } from "../../state/platform";

const store = usePlatformStore();
const route = useRoute();
const router = useRouter();

const childRoutes = computed(() =>
  [
    { name: "ops-overview", label: "运维总览", visible: store.hasPermission("ops.read") || store.hasPermission("system.read") },
    { name: "ops-schedule", label: "定时任务", visible: store.hasPermission("schedule.read") },
    { name: "ops-dictionaries", label: "数据字典", visible: store.hasPermission("dict.read") },
    { name: "ops-alerts", label: "告警通道", visible: store.hasPermission("ops.read") || store.hasPermission("settings.read") },
    { name: "ops-audit", label: "日志审计", visible: store.hasPermission("logs.read") },
    { name: "k6-workers", label: "k6 节点", visible: store.hasPermission("worker.read"), external: true },
  ].filter((item) => item.visible),
);

const pageTitle = computed(() => {
  if (route.name === "k6-workers" || route.path.startsWith("/k6-workers")) return "k6 节点";
  const hit = childRoutes.value.find((item) => item.name === route.name);
  return hit?.label ?? "运维管理";
});

const isTabActive = (name: string) => {
  if (name === "k6-workers") return route.name === "k6-workers";
  return route.name === name;
};

const goTab = (item: { name: string; external?: boolean }) => {
  if (item.external || item.name === "k6-workers") {
    void router.push({ name: "k6-workers" });
    return;
  }
  void router.push({ name: item.name });
};

const ensureVisibleChild = () => {
  const visible = childRoutes.value;
  if (!visible.length) return;
  if (route.name === "k6-workers") return;
  const currentAllowed = visible.some((item) => item.name === route.name);
  if (!currentAllowed || route.name === "ops") {
    const first = visible.find((item) => !item.external) || visible[0];
    void router.replace({ name: first.name });
  }
};

onMounted(() => ensureVisibleChild());
watch(
  () => [route.name, childRoutes.value.map((item) => item.name).join(",")],
  () => ensureVisibleChild(),
);
</script>

<template>
  <div class="ops-page ai-workspace ai-page-fill">
    <AiWorkspaceHero
      title="运维管理"
      :subtitle="`${pageTitle} · 可观测、可管控、可追溯`"
      badge="AI · OPS"
      status-label="运维域"
      status-tone="online"
    />

    <div class="ops-tabs">
      <button
        v-for="item in childRoutes"
        :key="item.name"
        type="button"
        class="ops-tab"
        :class="{ 'ops-tab--active': isTabActive(item.name) }"
        @click="() => goTab(item)"
      >
        {{ item.label }}
      </button>
    </div>

    <div class="ops-content ai-panel ai-fill-panel">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.ops-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 12px;
}
.ops-tab {
  border: 1px solid rgba(14, 165, 233, 0.25);
  background: rgba(255, 255, 255, 0.72);
  color: #0f172a;
  border-radius: 999px;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 13px;
}
.ops-tab--active {
  background: linear-gradient(135deg, #0891b2, #4f46e5);
  border-color: transparent;
  color: #fff;
}
.ops-content {
  border-radius: 16px;
  padding: 16px;
  min-height: 420px;
}
</style>
