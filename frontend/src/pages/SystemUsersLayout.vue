<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { provideRbacData } from "./rbac/useRbacData";
import { usePlatformStore } from "../state/platform";

const store = usePlatformStore();
const route = useRoute();
const router = useRouter();
const { load } = provideRbacData();

const childRoutes = computed(() =>
  [
    { name: "system-users-users", label: "用户列表", visible: store.hasPermission("user.manage") },
    {
      name: "system-users-departments",
      label: "用户部门",
      visible: store.hasAnyPermission(["org.read", "user.manage"]),
    },
    { name: "system-users-roles", label: "用户角色", visible: store.hasPermission("role.manage") },
    {
      name: "system-users-permissions",
      label: "用户权限",
      visible: store.hasPermission("permission.manage"),
    },
  ].filter((item) => item.visible),
);

const pageTitle = computed(() => {
  const hit = childRoutes.value.find((item) => item.name === route.name);
  return hit?.label ?? "用户管理";
});

const ensureVisibleChild = () => {
  const visible = childRoutes.value;
  if (!visible.length) return;
  const currentAllowed = visible.some((item) => item.name === route.name);
  if (!currentAllowed || route.name === "system-users") {
    void router.replace({ name: visible[0].name });
  }
};

onMounted(() => {
  void load();
  ensureVisibleChild();
});

watch(
  () => [route.name, childRoutes.value.map((item) => item.name).join(",")],
  () => ensureVisibleChild(),
);
</script>

<template>
  <div class="system-users-page ai-workspace ai-page-fill">
    <AiWorkspaceHero
      title="用户管理"
      :subtitle="`${pageTitle} · 用户、部门、角色与权限统一治理`"
      badge="AI · ACCESS"
      status-label="权限域就绪"
      status-tone="online"
    >
      <template #extra>
        <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="load">
          刷新
        </a-button>
      </template>
    </AiWorkspaceHero>

    <div class="system-users-content ai-panel ai-fill-panel">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.system-users-content {
  border-radius: 16px;
  padding: 16px;
}

.system-users-content :deep(.rbac-panel-card),
.system-users-content :deep(.rbac-split-left),
.system-users-content :deep(.rbac-split-right) {
  border-radius: 12px;
}

.system-users-content :deep(.rbac-filter-form) {
  margin-bottom: 12px;
}

.system-users-content :deep(.rbac-table-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
</style>
