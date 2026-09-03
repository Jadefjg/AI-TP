<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { createAsyncSection } from "../createAsyncSection";
import { useProjectScope } from "../../../composables/useProjectScope";
import { provideProjectAiContext } from "./ai/useProjectAiContext";

const router = useRouter();
const { projectId } = useProjectScope();
const { hasAiExecute, aiForm } = provideProjectAiContext();

const AiRequirementReviewTab = createAsyncSection(() => import("./ai/AiRequirementReviewTab.vue"));
const AiFunctionalCasesTab = createAsyncSection(() => import("./ai/AiFunctionalCasesTab.vue"));
const AiApiDslTab = createAsyncSection(() => import("./ai/AiApiDslTab.vue"));
const AiPerfTab = createAsyncSection(() => import("./ai/AiPerfTab.vue"));
const AiSecurityTab = createAsyncSection(() => import("./ai/AiSecurityTab.vue"));
const AiSharedPanels = createAsyncSection(() => import("./ai/AiSharedPanels.vue"));

const uiHref = computed(() => `/projects/${projectId.value}/ui`);
const openUiAgent = () => {
  void router.push(uiHref.value);
};
</script>

<template>
  <div>
    <a-card title="项目内 AI 工作台" class="ai-panel ai-panel--accent">
      <div class="ai-chip-rail">
        <span class="ai-chip ai-chip--live">Neural Pipeline</span>
        <span class="ai-chip">与侧栏 01–05 Agent 对齐</span>
      </div>
      <a-form layout="vertical">
        <a-form-item label="Base URL（DSL / 压测 / 扫描）">
          <a-input v-model="aiForm.baseUrl" />
        </a-form-item>
      </a-form>
      <a-result v-if="!hasAiExecute" status="info" title="只读模式" subtitle="需要 ai.execute 方可使用 AI 生成与调试" />
      <a-collapse v-else :default-active-key="['1']" class="project-ai-collapse">
        <a-collapse-item header="01 · 需求 Agent（评审 + 用例）" key="1">
          <AiRequirementReviewTab />
          <div class="project-ai-sub">
            <div class="project-ai-sub__title">功能用例生成</div>
            <AiFunctionalCasesTab />
          </div>
        </a-collapse-item>
        <a-collapse-item header="02 · UI Agent（Playwright）" key="2">
          <a-alert
            type="info"
            show-icon
            title="UI Agent 在独立工作台运行：由功能用例生成 Playwright DSL，并逐步/整段执行。"
            style="margin-bottom: 12px"
          />
          <a-button type="primary" @click="openUiAgent">打开项目 UI Agent</a-button>
          <a-button style="margin-left: 8px" @click="() => router.push({ path: '/ui-management', query: { projectId: String(projectId) } })">
            打开全局 02 UI Agent
          </a-button>
        </a-collapse-item>
        <a-collapse-item header="03 · 接口 Agent" key="3">
          <AiApiDslTab />
        </a-collapse-item>
        <a-collapse-item header="04 · 性能 Agent" key="4">
          <AiPerfTab />
        </a-collapse-item>
        <a-collapse-item header="05 · 安全 Agent" key="5">
          <AiSecurityTab />
        </a-collapse-item>
      </a-collapse>

      <AiSharedPanels />
    </a-card>
  </div>
</template>

<style src="../../../assets/project-section.css"></style>

<style scoped>
.project-ai-collapse :deep(.arco-collapse-item-header) {
  font-weight: 650;
  letter-spacing: 0.02em;
}
.project-ai-collapse :deep(.arco-collapse-item-active > .arco-collapse-item-header) {
  color: #0369a1;
}
.project-ai-sub {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed rgba(14, 165, 233, 0.25);
}
.project-ai-sub__title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}
</style>
