<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AiWorkspaceHero from "../../components/ai/AiWorkspaceHero.vue";
import { provideProjectScope } from "../../composables/useProjectScope";
import { rememberPipelineProjectId } from "../../constants/aiPipeline";
import { usePlatformStore } from "../../state/platform";

const route = useRoute();
const router = useRouter();
const store = usePlatformStore();
const { projectId, project, reloadProject } = provideProjectScope();

const navItems = computed(() => [
  { name: "project-cases", label: "用例", short: "01" },
  { name: "project-ai", label: "AI", short: "02" },
  { name: "project-runs", label: "运行", short: "03" },
  { name: "project-reports", label: "报告", short: "04" },
  { name: "project-workbench", label: "工作台", short: "05" },
  { name: "project-integrations", label: "集成", short: "06" },
  { name: "project-ui", label: "UI 自动化", short: "07" },
]);

const sourceLabel = computed(() => {
  const source = project.value?.repo_source;
  if (source === "remote") return "远程仓库";
  if (source === "deployed") return "已部署";
  if (source === "local") return "本地仓库";
  return source || "—";
});

onMounted(() => {
  void reloadProject();
});

watch(projectId, (id) => {
  rememberPipelineProjectId(id);
  void reloadProject();
});
</script>

<template>
  <div class="project-shell ai-workspace ai-page-fill">
    <AiWorkspaceHero
      :title="project?.name || `项目 #${projectId}`"
      :subtitle="`${sourceLabel} · ${(project?.repo_source === 'deployed' ? project?.code_root : project?.code_root) || '加载项目上下文中…'}`"
      badge="AI · PROJECT"
      :status-label="project ? '项目在线' : '加载中'"
      :status-tone="project ? 'online' : 'busy'"
    >
      <template #extra>
        <a-space>
          <a-button @click="router.push({ name: 'projects' })">返回列表</a-button>
          <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="reloadProject">
            刷新
          </a-button>
        </a-space>
      </template>
    </AiWorkspaceHero>

    <template v-if="project">
      <a-card class="ai-panel project-meta" :bordered="false">
        <a-descriptions :column="2" size="medium">
          <a-descriptions-item label="项目 ID">{{ project.id }}</a-descriptions-item>
          <a-descriptions-item label="来源">{{ sourceLabel }}</a-descriptions-item>
          <a-descriptions-item :label="project.repo_source === 'deployed' ? '访问地址' : '路径'" :span="2">
            {{ project.code_root }}
          </a-descriptions-item>
        </a-descriptions>
      </a-card>

      <nav class="project-nav" aria-label="项目模块">
        <button
          v-for="item in navItems"
          :key="item.name"
          type="button"
          class="project-nav__item"
          :class="{ 'project-nav__item--active': route.name === item.name }"
          @click="router.push({ name: item.name, params: { id: projectId } })"
        >
          <span class="project-nav__no">{{ item.short }}</span>
          <span class="project-nav__label">{{ item.label }}</span>
        </button>
      </nav>

      <div class="ai-fill-host">
        <router-view />
      </div>
    </template>
  </div>
</template>

<style scoped>
.project-meta {
  margin-bottom: 14px;
}

.project-nav {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 16px;
  padding: 10px;
  border: 1px solid rgba(14, 165, 233, 0.22);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(240, 249, 255, 0.92), rgba(255, 255, 255, 0.8));
}

.project-nav__item {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: rgba(14, 165, 233, 0.1);
  color: inherit;
  font: inherit;
  font-weight: 400;
  width: 100%;
  margin-top: 0;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease;
}

.project-nav__item:hover {
  background: rgba(14, 165, 233, 0.14);
  transform: translateY(-1px);
}

.project-nav__item--active {
  border-color: rgba(14, 165, 233, 0.4);
  background: rgba(14, 165, 233, 0.1);
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.08);
}

.project-nav__no {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #0284c7;
  white-space: nowrap;
}

.project-nav__label {
  font-size: 13px;
  font-weight: 650;
  color: var(--color-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 1100px) {
  .project-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .project-nav {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
