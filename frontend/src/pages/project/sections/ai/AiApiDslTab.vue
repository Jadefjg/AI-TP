<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { aiApi } from "../../../../api/ai";
import { useProjectAiContext } from "./useProjectAiContext";
import type { ApiRegressionSet } from "../../../../types";
import { DEFAULT_BASE_URL } from "../../../../constants/platformDefaults";

const {
  projectId,
  store,
  aiForm,
  hasAiExecute,
  apiAutomationArtifacts,
  pickArtifactRequest,
  loadAiArtifacts,
  requestPickArtifact,
  dslLastResult,
} = useProjectAiContext();

const dslEditor = reactive({
  artifactId: "",
  scriptContent: "",
});
const dslSteps = ref<Array<{ index: number; name: string; method?: string; url?: string }>>([]);
const dslAnalysis = ref<Record<string, unknown> | null>(null);
const apiRegressionSets = ref<ApiRegressionSet[]>([]);
const regressionForm = reactive({ name: "", caseIdsText: "", baseUrl: DEFAULT_BASE_URL });

const pickArtifactForEditor = (artifactId: number) => {
  dslEditor.artifactId = String(artifactId);
  const item = apiAutomationArtifacts.value.find((a) => Number(a.id) === artifactId);
  const payload = (item?.payload || {}) as Record<string, unknown>;
  dslEditor.scriptContent = String(payload.script_content || "");
  void previewDslScript();
};

watch(pickArtifactRequest, (artifactId) => {
  if (artifactId) {
    pickArtifactForEditor(artifactId);
    pickArtifactRequest.value = null;
  }
});

const loadApiRegressionSets = () =>
  store.runBackground(async () => {
    apiRegressionSets.value = await aiApi.listApiRegressionSets(projectId.value);
  });

void loadApiRegressionSets();

const previewDslScript = () =>
  store.wrap(async () => {
    const result = await aiApi.previewDsl(projectId.value, dslEditor.scriptContent, aiForm.baseUrl);
    dslSteps.value = (result.steps || []) as typeof dslSteps.value;
    store.setOut(result);
  });

const saveDslScript = () =>
  store.wrap(async () => {
    const aid = Number(dslEditor.artifactId);
    if (!aid) return;
    await aiApi.updateApiArtifactScript(projectId.value, aid, { script_content: dslEditor.scriptContent });
    await loadAiArtifacts();
    pickArtifactForEditor(aid);
  });

const runDslStep = (stepIndex: number) =>
  store.wrap(async () => {
    const result = await aiApi.executeDslStep(
      projectId.value,
      dslEditor.scriptContent,
      stepIndex,
      aiForm.baseUrl,
    );
    dslLastResult.value = result;
    store.setOut(result);
  });

const runFullDsl = () =>
  store.wrap(async () => {
    const aid = Number(dslEditor.artifactId);
    if (!aid) return;
    const result = await aiApi.executeApiArtifact(projectId.value, aid, {
      baseUrl: aiForm.baseUrl,
      scriptContent: dslEditor.scriptContent,
    });
    dslLastResult.value = result;
    store.setOut(result);
  });

const analyzeDslFailure = () =>
  store.wrap(async () => {
    const aid = Number(dslEditor.artifactId);
    if (!aid) return;
    const result = await aiApi.analyzeApiFailure(projectId.value, aid, {
      execution_result: dslLastResult.value || undefined,
      base_url: aiForm.baseUrl,
      rerun: !dslLastResult.value,
    });
    dslAnalysis.value = result;
    store.setOut(result);
  });

const createApiRegressionSet = () =>
  store.wrap(async () => {
    const caseIds = regressionForm.caseIdsText
      .split(/[,，\s]+/)
      .map((s) => Number(s.trim()))
      .filter((n) => n > 0);
    if (!caseIds.length) throw new Error("请填写至少一个 case ID");
    await aiApi.createApiRegressionSet(projectId.value, {
      name: regressionForm.name,
      case_ids: caseIds,
      base_url: regressionForm.baseUrl,
    });
    regressionForm.name = "";
    regressionForm.caseIdsText = "";
    await loadApiRegressionSets();
  });

const aiApiAutomation = () =>
  store.wrap(async () => {
    const caseId = aiForm.bindCaseId ? Number(aiForm.bindCaseId) : null;
    const result = await aiApi.aiApiAutomation(projectId.value, {
      case_info: aiForm.caseInfo,
      api_info: aiForm.apiInfo,
      case_id: caseId && !Number.isNaN(caseId) ? caseId : null,
    });
    store.setOut(result);
    await loadAiArtifacts();
    const firstId = result.persisted_ids?.[0];
    if (firstId) requestPickArtifact(firstId);
  });
</script>

<template>
  <a-textarea v-model="aiForm.caseInfo" placeholder="测试用例信息" :auto-size="{ minRows: 2 }" />
  <a-textarea v-model="aiForm.apiInfo" placeholder="接口基础信息" :auto-size="{ minRows: 2 }" />
  <a-input v-model="aiForm.bindCaseId" placeholder="绑定功能用例 ID（闭环回归）" style="margin-top: 8px" />
  <a-button type="primary" style="margin-top: 8px" @click="aiApiAutomation">生成脚本</a-button>

  <a-divider orientation="left">DSL 可视化编辑 / 单步调试</a-divider>
  <a-select
    v-model="dslEditor.artifactId"
    placeholder="选择 api_automation 产物"
    allow-search
    style="width: 100%; margin-bottom: 8px"
    @change="pickArtifactForEditor(Number(dslEditor.artifactId))"
  >
    <a-option v-for="a in apiAutomationArtifacts" :key="String(a.id)" :value="String(a.id)">
      #{{ a.id }} · case={{ a.case_id ?? "-" }} · {{ a.title }}
    </a-option>
  </a-select>
  <a-textarea
    v-model="dslEditor.scriptContent"
    placeholder="YAML DSL"
    :auto-size="{ minRows: 10 }"
    style="font-family: monospace"
  />
  <a-space wrap style="margin-top: 8px">
    <a-button v-if="hasAiExecute" @click="previewDslScript">解析步骤</a-button>
    <a-button v-if="hasAiExecute" type="outline" @click="saveDslScript">保存脚本</a-button>
    <a-button v-if="hasAiExecute" type="primary" @click="runFullDsl">执行全部</a-button>
    <a-button v-if="hasAiExecute" status="warning" @click="analyzeDslFailure">失败归因</a-button>
  </a-space>
  <a-table v-if="dslSteps.length" :data="dslSteps" :pagination="false" size="small" style="margin-top: 8px">
    <template #columns>
      <a-table-column title="#" data-index="index" :width="50" />
      <a-table-column title="步骤" data-index="name" />
      <a-table-column title="请求" :width="220">
        <template #cell="{ record }">{{ record.method }} {{ record.url }}</template>
      </a-table-column>
      <a-table-column title="操作" :width="100">
        <template #cell="{ record }">
          <a-button v-if="hasAiExecute" size="mini" @click="runDslStep(record.index)">单步</a-button>
        </template>
      </a-table-column>
    </template>
  </a-table>
  <pre v-if="dslLastResult" class="payload-pre" style="margin-top: 8px">{{ JSON.stringify(dslLastResult, null, 2) }}</pre>
  <pre v-if="dslAnalysis" class="payload-pre">{{ JSON.stringify(dslAnalysis, null, 2) }}</pre>

  <a-divider orientation="left">回归集（绑定 case_id）</a-divider>
  <a-form v-if="hasAiExecute" layout="inline" style="margin-bottom: 8px">
    <a-input v-model="regressionForm.name" placeholder="回归集名称" style="width: 140px" />
    <a-input v-model="regressionForm.caseIdsText" placeholder="用例 ID，逗号分隔" style="width: 180px" />
    <a-button type="primary" @click="createApiRegressionSet">创建</a-button>
    <a-button @click="loadApiRegressionSets">刷新</a-button>
  </a-form>
  <a-list :data="apiRegressionSets" size="small">
    <template #item="{ item }">
      <a-list-item-meta
        :title="item.name"
        :description="`cases: ${(item.case_ids || []).join(', ')} · ${item.base_url}`"
      />
    </template>
  </a-list>
</template>
