<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { RouterView } from "vue-router";
import { projectsApi } from "../api/projects";
import AppBrandMark from "../components/AppBrandMark.vue";
import UserSettingsModal from "../components/UserSettingsModal.vue";
import {
  buildPipelineQuery,
  recalledPipelineProjectId,
  rememberPipelineProjectId,
} from "../constants/aiPipeline";
import { usePlatformStore } from "../state/platform";
import type { Project } from "../types";

const store = usePlatformStore();
const route = useRoute();
const router = useRouter();
const collapsed = ref(false);
const showDebug = ref(false);
const settingsVisible = ref(false);
const settingsTab = ref<"profile" | "password" | "api">("profile");
const projects = ref<Project[]>([]);
const globalProjectId = ref<number | null>(null);

type NavLeaf = { type: "item"; to: string; label: string; permission: string };
type NavGroup = {
  type: "group";
  key: string;
  label: string;
  children: { to: string; label: string; permission: string | string[] }[];
};

const navEntries: Array<NavLeaf | NavGroup> = [
  { type: "item", to: "/dashboard", label: "首页", permission: "dashboard.read" },
  { type: "item", to: "/tasks", label: "任务中心", permission: "run.read" },
  { type: "item", to: "/projects", label: "项目管理", permission: "project.read" },
  {
    type: "group",
    key: "ai-pipeline",
    label: "智能流水",
    children: [
      { to: "/requirements", label: "01 需求 Agent", permission: "ai.read" },
      { to: "/ui-management", label: "02 UI Agent", permission: "ai.read" },
      { to: "/interface-management", label: "03 接口 Agent", permission: "ai.read" },
      { to: "/perf-management", label: "04 性能 Agent", permission: "ai.read" },
      { to: "/security-management", label: "05 安全 Agent", permission: "ai.read" },
    ],
  },
  {
    type: "group",
    key: "perf-ops",
    label: "运维管理",
    children: [{ to: "/k6-workers", label: "k6 节点", permission: "worker.read" }],
  },
  { type: "item", to: "/tenant", label: "租户管理", permission: "org.read" },
  {
    type: "group",
    key: "system-users",
    label: "用户管理",
    children: [
      { to: "/system-users/users", label: "用户列表", permission: "user.manage" },
      {
        to: "/system-users/departments",
        label: "用户部门",
        permission: ["org.read", "user.manage"],
      },
      { to: "/system-users/roles", label: "用户角色", permission: "role.manage" },
      { to: "/system-users/permissions", label: "用户权限", permission: "permission.manage" },
    ],
  },
  {
    type: "group",
    key: "system-info",
    label: "系统信息",
    children: [
      { to: "/system", label: "系统概览", permission: "system.read" },
      { to: "/logs", label: "操作日志", permission: "logs.read" },
    ],
  },
  {
    type: "group",
    key: "system-settings",
    label: "系统配置",
    children: [
      { to: "/settings", label: "平台配置", permission: "settings.read" },
      { to: "/ai-prompts", label: "AI Prompt", permission: "prompt.read" },
    ],
  },
];

const hasNavPermission = (permission: string | string[]) => {
  if (Array.isArray(permission)) {
    return store.hasAnyPermission(permission);
  }
  return store.hasPermission(permission);
};

const visibleNavEntries = computed(() =>
  navEntries
    .map((entry) => {
      if (entry.type === "item") {
        return hasNavPermission(entry.permission) ? entry : null;
      }
      const children = entry.children.filter((child) => hasNavPermission(child.permission));
      return children.length ? { ...entry, children } : null;
    })
    .filter(Boolean) as Array<NavLeaf | NavGroup>,
);

const openKeys = ref<string[]>(["ai-pipeline"]);

const selectedKey = computed(() => {
  if (route.path.startsWith("/billing")) return "/tenant";
  if (route.path.startsWith("/tasks")) return "/tasks";

  const groupChildren = navEntries.flatMap((e) => (e.type === "group" ? e.children : []));
  // Exact match first, then longest prefix — avoids wrong sibling highlight.
  const exact = groupChildren.find((c) => route.path === c.to);
  if (exact) return exact.to;
  const prefixHits = groupChildren
    .filter((c) => route.path.startsWith(`${c.to}/`))
    .sort((a, b) => b.to.length - a.to.length);
  if (prefixHits[0]) return prefixHits[0].to;

  const flat = visibleNavEntries.value.filter((e): e is NavLeaf => e.type === "item");
  const flatExact = flat.find((item) => route.path === item.to);
  if (flatExact) return flatExact.to;
  const flatPrefix = [...flat]
    .filter((item) => route.path.startsWith(`${item.to}/`) || route.path.startsWith(item.to))
    .sort((a, b) => b.to.length - a.to.length);
  return flatPrefix[0]?.to || "/dashboard";
});

const isPipelineRoute = computed(() =>
  [
    "/requirements",
    "/cases",
    "/ui-management",
    "/interface-management",
    "/perf-management",
    "/security-management",
  ].some((prefix) => route.path === prefix || route.path.startsWith(`${prefix}/`)),
);

const isProjectWorkspaceRoute = computed(() => {
  const name = typeof route.name === "string" ? route.name : "";
  return name.startsWith("project-") && Boolean(route.params.id);
});

const projectSelectOptions = computed(() =>
  [...projects.value].sort((a, b) => a.id - b.id),
);

watch(
  () => route.path,
  (path) => {
    const keysToOpen: string[] = ["ai-pipeline"];
    if (path.startsWith("/system-users")) keysToOpen.push("system-users");
    if (path.startsWith("/k6-workers")) keysToOpen.push("perf-ops");
    if (path === "/system" || path.startsWith("/system/") || path.startsWith("/logs")) {
      keysToOpen.push("system-info");
    }
    if (path.startsWith("/settings") || path.startsWith("/ai-prompts")) {
      keysToOpen.push("system-settings");
    }
    for (const key of keysToOpen) {
      if (!openKeys.value.includes(key)) {
        openKeys.value = [...openKeys.value, key];
      }
    }
  },
  { immediate: true },
);

watch(
  () => route.query.projectId,
  (raw) => {
    const n = Number(Array.isArray(raw) ? raw[0] : raw);
    if (!Number.isFinite(n) || n <= 0) return;
    if (globalProjectId.value === n) return;
    if (projects.value.length && !projects.value.some((p) => p.id === n)) return;
    globalProjectId.value = n;
    rememberPipelineProjectId(n);
  },
);

watch(
  () => route.params.id,
  (raw) => {
    if (!isProjectWorkspaceRoute.value) return;
    const n = Number(Array.isArray(raw) ? raw[0] : raw);
    if (!Number.isFinite(n) || n <= 0) return;
    if (globalProjectId.value === n) return;
    globalProjectId.value = n;
    rememberPipelineProjectId(n);
  },
  { immediate: true },
);

const avatarText = computed(() => {
  const user = store.currentUser.value;
  if (!user) return "?";
  const name = user.display_name || user.username;
  return name.slice(0, 1).toUpperCase();
});

const loadProjects = async () => {
  if (!store.hasPermission("project.read") && !store.hasPermission("ai.read")) return;
  try {
    projects.value = await projectsApi.listProjects();
    const fromParam = Number(
      Array.isArray(route.params.id) ? route.params.id[0] : route.params.id,
    );
    const fromQuery = Number(
      Array.isArray(route.query.projectId) ? route.query.projectId[0] : route.query.projectId,
    );
    const preferredCandidates = [
      isProjectWorkspaceRoute.value && Number.isFinite(fromParam) && fromParam > 0
        ? Math.trunc(fromParam)
        : null,
      Number.isFinite(fromQuery) && fromQuery > 0 ? Math.trunc(fromQuery) : null,
      recalledPipelineProjectId(),
      globalProjectId.value,
    ].filter((v): v is number => typeof v === "number" && v > 0);

    const preferred = preferredCandidates.find((id) => projects.value.some((p) => p.id === id));
    if (preferred) {
      globalProjectId.value = preferred;
      rememberPipelineProjectId(preferred);
    } else if (projects.value.length) {
      globalProjectId.value = [...projects.value].sort((a, b) => a.id - b.id)[0].id;
      rememberPipelineProjectId(globalProjectId.value);
    }
  } catch (error) {
    projects.value = [];
    Message.warning(error instanceof Error ? error.message : "项目列表加载失败");
  }
};

const onProjectPopupVisibleChange = (visible: boolean) => {
  if (visible) void loadProjects();
};

const onGlobalProjectChange = (value: string | number | boolean) => {
  const id = Number(value);
  if (!Number.isFinite(id) || id <= 0) return;
  if (!projects.value.some((p) => p.id === id)) {
    Message.warning("所选项目不在当前列表中，请刷新后重试");
    void loadProjects();
    return;
  }
  globalProjectId.value = id;
  rememberPipelineProjectId(id);

  if (isProjectWorkspaceRoute.value) {
    const routeName =
      typeof route.name === "string" && route.name.startsWith("project-")
        ? route.name
        : "project-cases";
    void router.push({
      name: routeName,
      params: { ...route.params, id: String(id) },
      query: route.query,
    });
    return;
  }

  if (isPipelineRoute.value) {
    void router.replace({
      name: route.name || undefined,
      params: route.params,
      query: {
        ...route.query,
        ...buildPipelineQuery({ projectId: id }),
      },
    });
    return;
  }

  if (route.path === "/projects" || route.path.startsWith("/projects/")) {
    void router.push({ name: "project-cases", params: { id: String(id) } });
  }
};

const onMenuClick = (key: string) => {
  const pipelineKeys = [
    "/requirements",
    "/cases",
    "/ui-management",
    "/interface-management",
    "/perf-management",
    "/security-management",
  ];
  const toPipeline = pipelineKeys.some((p) => key === p || key.startsWith(`${p}/`));
  const query =
    toPipeline || isPipelineRoute.value
      ? buildPipelineQuery({ projectId: globalProjectId.value })
      : undefined;
  void router.push(query ? { path: key, query } : key);
};

const onOpenChange = (keys: string[]) => {
  openKeys.value = keys;
};

const openSettings = (tab: "profile" | "password" | "api") => {
  settingsTab.value = tab;
  settingsVisible.value = true;
};

const onUserMenuSelect = (key: string) => {
  if (key === "profile") {
    openSettings("profile");
    return;
  }
  if (key === "password") {
    openSettings("password");
    return;
  }
  if (key === "api") {
    openSettings("api");
    return;
  }
  if (key === "logout") {
    void store.wrap(async () => {
      await store.logout();
      await router.replace({ name: "login" });
    });
  }
};

const onDropdownSelect = (value: string | number | Record<string, unknown> | undefined) => {
  if (typeof value === "string") {
    onUserMenuSelect(value);
  }
};

onMounted(() => {
  void loadProjects();
});
</script>

<template>
  <a-layout class="arco-shell">
    <a-layout-sider
      class="shell-sider"
      :collapsed="collapsed"
      collapsible
      :width="248"
      @collapse="(v: boolean) => (collapsed = v)"
    >
      <div class="brand">
        <AppBrandMark compact />
        <div v-if="!collapsed">
          <h1>AI-TP</h1>
          <p>AI 测试中枢</p>
        </div>
      </div>
      <div class="shell-menu-scroll">
        <a-menu
          class="shell-menu"
          theme="dark"
          :selected-keys="[selectedKey]"
          :open-keys="openKeys"
          @update:open-keys="onOpenChange"
        >
          <template v-for="entry in visibleNavEntries" :key="entry.type === 'group' ? entry.key : entry.to">
            <a-sub-menu v-if="entry.type === 'group'" :key="entry.key">
              <template #title>{{ entry.label }}</template>
              <a-menu-item
                v-for="child in entry.children"
                :key="child.to"
                @click="() => onMenuClick(child.to)"
              >
                {{ child.label }}
              </a-menu-item>
            </a-sub-menu>
            <a-menu-item v-else :key="entry.to" @click="() => onMenuClick(entry.to)">
              {{ entry.label }}
            </a-menu-item>
          </template>
        </a-menu>
      </div>
    </a-layout-sider>

    <a-layout class="shell-main">
      <a-layout-header class="top-header">
        <div class="top-header__left">
          <a-typography-title :heading="5" class="top-header__title">
            测试平台控制台
          </a-typography-title>
          <span class="top-header__chip" :class="{ 'top-header__chip--pipeline': isPipelineRoute }">
            <span class="top-header__chip-dot" />
            NEURAL · READY
          </span>
        </div>
        <div v-if="store.currentUser.value" class="top-header__actions">
          <a-select
            v-if="store.hasPermission('project.read') || store.hasPermission('ai.read') || store.hasPermission('case.read')"
            :model-value="globalProjectId ?? undefined"
            allow-search
            placeholder="选择项目"
            class="top-header__project"
            popup-container="body"
            :trigger-props="{ autoFitPopupMinWidth: true, updateAtScroll: true }"
            @popup-visible-change="onProjectPopupVisibleChange"
            @change="onGlobalProjectChange"
          >
            <a-option
              v-for="item in projectSelectOptions"
              :key="item.id"
              :value="item.id"
              :label="`#${item.id} · ${item.name}`"
            >
              <span class="top-header__project-option">
                <span class="top-header__project-id">#{{ item.id }}</span>
                <span>{{ item.name }}</span>
              </span>
            </a-option>
          </a-select>
          <a-dropdown trigger="click" position="br" @select="onDropdownSelect">
            <a-avatar :size="32" class="user-avatar user-trigger">{{ avatarText }}</a-avatar>
            <template #content>
              <a-doption value="profile">基本信息</a-doption>
              <a-doption value="password">修改密码</a-doption>
              <a-doption value="api">接口信息</a-doption>
              <a-doption value="logout">退出</a-doption>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>
      <a-layout-content class="main-content">
        <div class="main-content__scroll">
          <div class="main-content__body">
            <RouterView />
          </div>
          <section v-if="showDebug" class="debug-panel">
            <div class="debug-panel__header">
              <span class="debug-panel__chip">
                <span class="debug-panel__dot" />
                DEBUG · STREAM
              </span>
              <a-space>
                <a-button size="mini" type="text" class="debug-panel__btn" @click="store.output.value = ''">
                  清空
                </a-button>
                <a-button size="mini" type="text" class="debug-panel__btn" @click="showDebug = false">
                  隐藏
                </a-button>
              </a-space>
            </div>
            <pre class="debug-pre">{{ store.output.value || "// 暂无调试输出 · waiting for agent events" }}</pre>
          </section>
          <a-button v-else size="mini" type="text" class="debug-toggle" @click="showDebug = true">
            <span class="debug-toggle__chip">DEBUG</span>
            显示调试流
          </a-button>
        </div>
      </a-layout-content>
    </a-layout>

    <UserSettingsModal v-model:visible="settingsVisible" :initial-tab="settingsTab" />
  </a-layout>
</template>

<style scoped>
.arco-shell {
  height: 100vh;
  max-height: 100vh;
  overflow: hidden;
  background: transparent;
}

.shell-sider {
  height: 100vh !important;
  max-height: 100vh;
  overflow: hidden !important;
  background:
    radial-gradient(ellipse 80% 40% at 20% 0%, rgba(14, 165, 233, 0.22), transparent 55%),
    linear-gradient(180deg, #07111f 0%, #0b1220 55%, #0a1628 100%) !important;
  border-right: 1px solid rgba(56, 189, 248, 0.12);
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.03);
}

.shell-sider :deep(.arco-layout-sider-children) {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
}

.shell-menu-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-bottom: 8px;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(56, 189, 248, 0.55) rgba(15, 23, 42, 0.35);
}

.shell-menu-scroll::-webkit-scrollbar {
  width: 8px;
}

.shell-menu-scroll::-webkit-scrollbar-track {
  margin: 6px 0;
  background: rgba(15, 23, 42, 0.45);
  border-radius: 999px;
}

.shell-menu-scroll::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(34, 211, 238, 0.55), rgba(14, 165, 233, 0.4));
  border-radius: 999px;
  border: 2px solid rgba(15, 23, 42, 0.35);
}

.shell-menu-scroll::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(34, 211, 238, 0.8), rgba(14, 165, 233, 0.65));
}

.shell-sider :deep(.arco-menu) {
  background: transparent !important;
  height: auto;
  overflow: visible;
  color: #e2e8f0;
}

.shell-sider :deep(.arco-menu-inner) {
  background: transparent !important;
}

.shell-sider :deep(.arco-menu-item),
.shell-sider :deep(.arco-menu-inline-header),
.shell-sider :deep(.arco-menu-pop-header) {
  color: #e2e8f0 !important;
  background: transparent !important;
  border-radius: 10px;
  margin: 2px 8px;
  font-weight: 500;
}

.shell-sider :deep(.arco-menu-item .arco-icon),
.shell-sider :deep(.arco-menu-inline-header .arco-icon),
.shell-sider :deep(.arco-menu-icon-suffix) {
  color: #94a3b8 !important;
}

.shell-sider :deep(.arco-menu-item:hover),
.shell-sider :deep(.arco-menu-inline-header:hover),
.shell-sider :deep(.arco-menu-pop-header:hover) {
  background: rgba(14, 165, 233, 0.16) !important;
  color: #f8fafc !important;
}

.shell-sider :deep(.arco-menu-item.arco-menu-selected) {
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.38), rgba(14, 165, 233, 0.12)) !important;
  color: #ffffff !important;
  box-shadow: inset 3px 0 0 #22d3ee;
}

.shell-sider :deep(.arco-menu-item.arco-menu-selected .arco-icon),
.shell-sider :deep(.arco-menu-item:hover .arco-icon),
.shell-sider :deep(.arco-menu-inline-header:hover .arco-icon),
.shell-sider :deep(.arco-menu-item.arco-menu-selected .arco-menu-icon-suffix),
.shell-sider :deep(.arco-menu-inline-header:hover .arco-menu-icon-suffix) {
  color: #e0f2fe !important;
}

.shell-sider :deep(.arco-menu-inline-content) {
  background: transparent !important;
}

.shell-sider :deep(.arco-menu-inline-content .arco-menu-item) {
  color: #cbd5e1 !important;
  padding-left: 28px !important;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}

.shell-sider :deep(.arco-menu-inline-content .arco-menu-item.arco-menu-selected) {
  color: #ffffff !important;
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.28), rgba(14, 165, 233, 0.06)) !important;
  box-shadow: inset 3px 0 0 #22d3ee;
}

.shell-sider :deep(.arco-menu-selected-label) {
  display: none;
}

.shell-sider :deep(.arco-layout-sider-trigger) {
  flex-shrink: 0;
  background: rgba(15, 23, 42, 0.65);
  border-top: 1px solid rgba(56, 189, 248, 0.12);
  color: #94a3b8;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  padding: 18px 16px 14px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.1);
}

.brand h1 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0.06em;
  color: #f8fafc;
  font-weight: 700;
}

.brand p {
  margin: 2px 0 0;
  color: rgba(148, 163, 184, 0.9);
  font-size: 12px;
  letter-spacing: 0.04em;
}

.shell-main {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-height: 100vh;
  overflow: hidden;
  min-width: 0;
}

.top-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  flex-shrink: 0;
  padding: 0 20px;
  box-sizing: border-box;
  background:
    linear-gradient(90deg, rgba(14, 165, 233, 0.08), transparent 42%),
    rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}

.top-header__left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.top-header__title {
  margin: 0 !important;
  line-height: 1.2;
  letter-spacing: 0.02em;
}

.top-header__chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #0369a1;
  background: rgba(14, 165, 233, 0.12);
  border: 1px solid rgba(14, 165, 233, 0.22);
}

.top-header__chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22d3ee;
  box-shadow: 0 0 0 0 rgba(34, 211, 238, 0.5);
  animation: neural-pulse 1.8s ease-out infinite;
}

.top-header__chip--pipeline {
  color: #0c4a6e;
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.18), rgba(34, 211, 238, 0.1));
  border-color: rgba(14, 165, 233, 0.4);
  box-shadow: 0 0 16px rgba(14, 165, 233, 0.15);
}

@keyframes neural-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(34, 211, 238, 0.5);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(34, 211, 238, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(34, 211, 238, 0);
  }
}

.top-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.top-header__project {
  width: 260px;
}

.top-header__project-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.top-header__project-id {
  color: var(--color-text-3, #86909c);
  font-variant-numeric: tabular-nums;
}

.user-trigger {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.user-avatar {
  background: linear-gradient(135deg, #0ea5e9, #0284c7);
  color: #fff;
  font-weight: 600;
  flex-shrink: 0;
  transition: box-shadow 0.2s;
}

.user-avatar:hover {
  box-shadow: 0 4px 14px rgba(14, 165, 233, 0.4);
}

.main-content {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  padding: 0;
  background: transparent;
  overflow: hidden;
}

.main-content__scroll {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 16px 20px 12px;
  scrollbar-width: thin;
  scrollbar-color: rgba(14, 165, 233, 0.45) transparent;
  background:
    radial-gradient(ellipse 60% 30% at 100% 0%, rgba(14, 165, 233, 0.06), transparent 50%),
    transparent;
}

.main-content__scroll::-webkit-scrollbar {
  width: 8px;
}

.main-content__scroll::-webkit-scrollbar-track {
  background: transparent;
}

.main-content__scroll::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(14, 165, 233, 0.55), rgba(2, 132, 199, 0.4));
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: padding-box;
}

.main-content__scroll::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(14, 165, 233, 0.75), rgba(2, 132, 199, 0.6));
  background-clip: padding-box;
}

.main-content__body {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  min-width: 0;
  width: 100%;
}

/* Only list-style fill pages stretch into leftover viewport height */
.main-content__body:has(> .ai-page-fill) {
  flex: 1 0 auto;
}

.main-content__body > * {
  flex: 0 0 auto;
  width: 100%;
  min-width: 0;
}

.main-content__body > .ai-page-fill {
  flex: 1 0 auto;
}

.debug-toggle {
  margin-top: 8px;
  flex-shrink: 0;
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #0369a1 !important;
}

.debug-toggle__chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0369a1;
  background: rgba(14, 165, 233, 0.12);
  border: 1px solid rgba(14, 165, 233, 0.28);
}

.debug-panel {
  margin-top: 16px;
  flex-shrink: 0;
  border: 1px solid rgba(56, 189, 248, 0.28);
  border-radius: 14px;
  background:
    radial-gradient(ellipse at top left, rgba(14, 165, 233, 0.18), transparent 45%),
    #0b1220;
  overflow: hidden;
  box-shadow: 0 12px 28px rgba(2, 132, 199, 0.12);
}

.debug-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.18);
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.12), rgba(15, 23, 42, 0.95));
}

.debug-panel__chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #7dd3fc;
}

.debug-panel__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22d3ee;
  box-shadow: 0 0 0 0 rgba(34, 211, 238, 0.5);
  animation: neural-pulse 1.8s ease-out infinite;
}

.debug-panel__btn {
  color: #7dd3fc !important;
}

.debug-pre {
  margin: 0;
  min-height: 280px;
  max-height: min(55vh, 560px);
  overflow: auto;
  padding: 14px 16px;
  font-size: 12px;
  line-height: 1.55;
  font-family: "JetBrains Mono", ui-monospace, Menlo, Monaco, Consolas, monospace;
  color: #cbd5e1;
  background: transparent;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
