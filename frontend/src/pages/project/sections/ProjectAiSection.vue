<script setup lang="ts">
import { createAsyncSection } from "../createAsyncSection";
import { provideProjectAiContext } from "./ai/useProjectAiContext";

const { hasAiExecute, aiForm } = provideProjectAiContext();

const AiRequirementReviewTab = createAsyncSection(() => import("./ai/AiRequirementReviewTab.vue"));
const AiFunctionalCasesTab = createAsyncSection(() => import("./ai/AiFunctionalCasesTab.vue"));
const AiApiDslTab = createAsyncSection(() => import("./ai/AiApiDslTab.vue"));
const AiPerfTab = createAsyncSection(() => import("./ai/AiPerfTab.vue"));
const AiSecurityTab = createAsyncSection(() => import("./ai/AiSecurityTab.vue"));
const AiSharedPanels = createAsyncSection(() => import("./ai/AiSharedPanels.vue"));
</script>

<template>
  <div>
    <a-card title="项目内 AI 工作台" class="ai-panel ai-panel--accent">
      <div class="ai-chip-rail">
        <span class="ai-chip ai-chip--live">Neural Pipeline</span>
        <span class="ai-chip">01–05 模块</span>
      </div>
      <a-form layout="vertical">
        <a-form-item label="Base URL（DSL / 压测 / 扫描）">
          <a-input v-model="aiForm.baseUrl" />
        </a-form-item>
      </a-form>
      <a-result v-if="!hasAiExecute" status="info" title="只读模式" subtitle="需要 ai.execute 方可使用 AI 生成与调试" />
      <a-collapse v-else :default-active-key="['1']" class="project-ai-collapse">
        <a-collapse-item header="01 · 需求预评审" key="1">
          <AiRequirementReviewTab />
        </a-collapse-item>
        <a-collapse-item header="02 · 功能用例" key="2">
          <AiFunctionalCasesTab />
        </a-collapse-item>
        <a-collapse-item header="03 · 接口自动化 DSL" key="3">
          <AiApiDslTab />
        </a-collapse-item>
        <a-collapse-item header="04 · 性能压测 + 监控" key="4">
          <AiPerfTab />
        </a-collapse-item>
        <a-collapse-item header="05 · 安全扫描" key="5">
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
</style>
