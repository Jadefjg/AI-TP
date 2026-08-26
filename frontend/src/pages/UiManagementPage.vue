<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { casesApi } from "../api/cases";
import { projectsApi } from "../api/projects";
import { previewUiScriptLocally, uiAutomationApi } from "../api/uiAutomation";
import AiBusyBanner from "../components/ai/AiBusyBanner.vue";
import AiPipelineBar from "../components/ai/AiPipelineBar.vue";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import {
  buildPipelineQuery,
  parsePipelineQuery,
  recalledPipelineProjectId,
  rememberPipelineProjectId,
} from "../constants/aiPipeline";
import { resolveProjectBaseUrl } from "../constants/projectDefaults";
import { usePlatformStore } from "../state/platform";
import type { FunctionalCase, Project } from "../types";

const store = usePlatformStore();
const router = useRouter();
const route = useRoute();

const projects = ref<Project[]>([]);
const projectId = ref<number | null>(null);
const cases = ref<FunctionalCase[]>([]);
const selectedCaseId = ref<number | null>(null);
const preview = ref<Record<string, unknown> | null>(null);
const stepResult = ref<Record<string, unknown> | null>(null);
const agentResult = ref<Record<string, unknown> | null>(null);
const stepIndex = ref(0);
const busyAction = ref<"" | "generate" | "preview" | "step" | "agent" | "save">("");

const defaultUiBase = () => {
  if (typeof window !== "undefined") return window.location.origin;
  return "http://127.0.0.1:5174";
};

const scriptJson = ref(
  `{\n  "version": "1",\n  "base_url": "${defaultUiBase()}",\n  "steps": []\n}`,
);

const canCaseRead = computed(() => store.hasPermission("case.read"));
const canCaseWrite = computed(() => store.hasPermission("case.write"));

const selectedProject = computed(
  () => projects.value.find((item) => item.id === projectId.value) ?? null,
);

const selectedCase = computed(
  () => cases.value.find((row) => row.id === selectedCaseId.value) ?? null,
);

const pipelineHandoff = computed(() => ({
  projectId: projectId.value,
  caseId: selectedCaseId.value,
}));

const stepCount = computed(() => {
  const steps = (preview.value?.steps as unknown[]) || [];
  if (Array.isArray(steps) && steps.length) return steps.length;
  try {
    const doc = JSON.parse(scriptJson.value) as { steps?: unknown[] };
    return Array.isArray(doc.steps) ? doc.steps.length : 0;
  } catch {
    return 0;
  }
});

const maxStepIndex = computed(() => Math.max(0, stepCount.value - 1));
const agentTraces = computed(() => {
  const traces = agentResult.value?.traces;
  return Array.isArray(traces) ? traces : [];
});

const ensureProject = () => {
  if (!projectId.value) {
    Message.warning("请先选择项目");
    return false;
  }
  return true;
};

const parseScriptJson = (): unknown | null => {
  try {
    return JSON.parse(scriptJson.value);
  } catch {
    Message.warning("脚本 JSON 格式无效，请检查后再试");
    return null;
  }
};

const withResolvedBase = (uiScript: unknown, baseUrl: string): unknown => {
  if (Array.isArray(uiScript)) {
    return { version: "1", base_url: baseUrl, steps: uiScript };
  }
  if (uiScript && typeof uiScript === "object") {
    return { ...(uiScript as Record<string, unknown>), base_url: baseUrl };
  }
  return { version: "1", base_url: baseUrl, steps: [] };
};

const scriptBaseUrl = (uiScript: unknown): string => {
  const pageOrigin = defaultUiBase();
  const projectUrl = resolveProjectBaseUrl(selectedProject.value);
  let value = "";
  if (uiScript && typeof uiScript === "object" && "base_url" in uiScript) {
    const raw = (uiScript as { base_url?: unknown }).base_url;
    if (typeof raw === "string" && raw.trim()) value = raw.trim().replace(/\/$/, "");
  }
  if (!value) {
    if (selectedProject.value?.repo_source === "deployed" && /^https?:\/\//i.test(projectUrl)) {
      return projectUrl;
    }
    return pageOrigin;
  }
  if (
    typeof window !== "undefined" &&
    /^https?:\/\/(127\.0\.0\.1|localhost):(5173|5174|5175)$/i.test(value) &&
    pageOrigin !== value
  ) {
    return pageOrigin;
  }
  return value;
};

const syncEditorBaseUrl = (baseUrl: string) => {
  const parsed = parseScriptJson();
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return;
  scriptJson.value = JSON.stringify({ ...(parsed as Record<string, unknown>), base_url: baseUrl }, null, 2);
};

const loadProjects = () =>
  store.wrap(async () => {
    projects.value = await projectsApi.listProjects();
    const fromQuery = parsePipelineQuery(route.query as Record<string, unknown>).projectId;
    const preferred = fromQuery || recalledPipelineProjectId();
    if (preferred && projects.value.some((item) => item.id === preferred)) {
      projectId.value = preferred;
    } else if (!projectId.value && projects.value.length) {
      projectId.value = projects.value[0].id;
    }
    rememberPipelineProjectId(projectId.value);
  });

const loadScript = async () => {
  if (!projectId.value || !selectedCaseId.value) return;
  const data = await uiAutomationApi.getCaseScript(projectId.value, selectedCaseId.value);
  const baseUrl = scriptBaseUrl(data.ui_script);
  scriptJson.value = JSON.stringify(withResolvedBase(data.ui_script, baseUrl), null, 2);
};

const loadCases = () =>
  store.runBackground(async () => {
    if (!canCaseRead.value || !projectId.value) {
      cases.value = [];
      selectedCaseId.value = null;
      return;
    }
    cases.value = await casesApi.listCases(projectId.value);
    const wanted = parsePipelineQuery(route.query as Record<string, unknown>).caseId;
    if (wanted && cases.value.some((row) => row.id === wanted)) {
      selectedCaseId.value = wanted;
    } else if (!cases.value.some((row) => row.id === selectedCaseId.value)) {
      selectedCaseId.value = cases.value[0]?.id ?? null;
    }
    if (selectedCaseId.value) {
      await loadScript();
    }
  });

const selectCase = (caseId: number) => {
  selectedCaseId.value = caseId;
  preview.value = null;
  stepResult.value = null;
  agentResult.value = null;
  void store.wrap(loadScript);
};

const generateFromCase = () => {
  if (!ensureProject() || !selectedCaseId.value) {
    Message.warning("请先选择功能用例");
    return;
  }
  busyAction.value = "generate";
  void store
    .wrap(async () => {
      const data = await uiAutomationApi.generateFromCase(projectId.value!, selectedCaseId.value!);
      const baseUrl = scriptBaseUrl(data.ui_script);
      const payload = withResolvedBase(data.ui_script, baseUrl);
      scriptJson.value = JSON.stringify(payload, null, 2);
      try {
        preview.value = await uiAutomationApi.preview(projectId.value!, payload, baseUrl);
      } catch {
        preview.value = previewUiScriptLocally(payload, baseUrl);
      }
      stepResult.value = null;
      agentResult.value = null;
      const count = Array.isArray(preview.value?.steps) ? preview.value.steps.length : 0;
      Message.success(`GUI Agent 已从用例生成 Playwright DSL（${count} 步），目标 ${baseUrl}`);
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const runPreview = () => {
  if (!ensureProject()) return;
  const uiScript = parseScriptJson();
  if (!uiScript) return;
  busyAction.value = "preview";
  void store
    .wrap(async () => {
      const baseUrl = scriptBaseUrl(uiScript);
      const payload = withResolvedBase(uiScript, baseUrl);
      syncEditorBaseUrl(baseUrl);
      try {
        preview.value = await uiAutomationApi.preview(projectId.value!, payload, baseUrl);
      } catch (error) {
        preview.value = previewUiScriptLocally(payload, baseUrl);
        const msg = error instanceof Error ? error.message : String(error);
        Message.warning(`后端预览失败，已使用本地解析：${msg}`);
      }
      const count = Array.isArray(preview.value?.steps) ? preview.value.steps.length : 0;
      if (count) Message.success(`已解析 ${count} 个 GUI 步骤`);
      else Message.warning("脚本暂无步骤，请先「从用例生成」或编辑 steps");
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const runStep = () => {
  if (!ensureProject()) return;
  if (stepCount.value <= 0) {
    Message.warning("当前脚本没有可执行步骤");
    return;
  }
  const uiScript = parseScriptJson();
  if (!uiScript) return;
  const index = Math.min(Math.max(0, stepIndex.value), maxStepIndex.value);
  stepIndex.value = index;
  busyAction.value = "step";
  void store
    .wrap(async () => {
      const baseUrl = scriptBaseUrl(uiScript);
      const payload = withResolvedBase(uiScript, baseUrl);
      syncEditorBaseUrl(baseUrl);
      stepResult.value = await uiAutomationApi.executeStep(projectId.value!, payload, index, baseUrl);
      const status = String(stepResult.value?.status || "");
      if (status === "skipped") {
        const reason = (stepResult.value?.detail as { reason?: string } | undefined)?.reason || "步骤已跳过";
        Message.warning(reason);
        return;
      }
      if (status === "failed" || status === "error") {
        const detailReason = (stepResult.value?.detail as { reason?: string } | undefined)?.reason;
        Message.error(detailReason || `步骤 #${index} 执行失败`);
        return;
      }
      Message.success(`已执行到步骤 #${index}，目标 ${baseUrl}`);
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const runAgent = () => {
  if (!ensureProject()) return;
  const uiScript = parseScriptJson();
  if (!uiScript) return;
  if (stepCount.value <= 0) {
    Message.warning("请先生成或预览步骤，再交给 Playwright GUI Agent 执行");
    return;
  }
  busyAction.value = "agent";
  void store
    .wrap(async () => {
      const baseUrl = scriptBaseUrl(uiScript);
      const payload = withResolvedBase(uiScript, baseUrl);
      syncEditorBaseUrl(baseUrl);
      agentResult.value = await uiAutomationApi.executeAgent(projectId.value!, payload, baseUrl);
      const status = String(agentResult.value?.status || "");
      if (status === "skipped") {
        const reason = (agentResult.value?.detail as { reason?: string } | undefined)?.reason || "Agent 已跳过";
        Message.warning(reason);
        return;
      }
      if (status === "failed" || status === "error") {
        const detailReason = (agentResult.value?.detail as { reason?: string } | undefined)?.reason;
        Message.error(detailReason || "GUI Agent 执行失败");
        return;
      }
      Message.success(`Playwright GUI Agent 已跑完 ${stepCount.value} 步`);
      Modal.confirm({
        title: "继续下一阶段？",
        content: "UI Agent 已完成。是否带着当前用例进入接口 Agent？",
        okText: "去接口 Agent",
        cancelText: "留在本页",
        onOk: () => goInterface(),
      });
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const saveScript = () => {
  if (!ensureProject() || !selectedCaseId.value) {
    Message.warning("请先选择功能用例");
    return;
  }
  const uiScript = parseScriptJson();
  if (!uiScript) return;
  busyAction.value = "save";
  void store
    .wrap(async () => {
      await uiAutomationApi.updateCaseScript(projectId.value!, selectedCaseId.value!, uiScript);
      Message.success("UI 脚本已保存到当前用例");
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const goRequirements = () => {
  void router.push({
    name: "requirements",
    query: buildPipelineQuery({ projectId: projectId.value }),
  });
};

const goCases = () => {
  void router.push({
    name: "cases",
    query: buildPipelineQuery({ projectId: projectId.value, caseId: selectedCaseId.value }),
  });
};

const goInterface = () => {
  rememberPipelineProjectId(projectId.value);
  void router.push({
    name: "interface-management",
    query: buildPipelineQuery({
      projectId: projectId.value,
      caseId: selectedCaseId.value,
    }),
  });
};

watch(projectId, (value) => {
  rememberPipelineProjectId(value);
  preview.value = null;
  stepResult.value = null;
  agentResult.value = null;
  void loadCases();
});

watch(stepCount, (count) => {
  if (count <= 0) {
    stepIndex.value = 0;
    return;
  }
  if (stepIndex.value > count - 1) stepIndex.value = count - 1;
});

onMounted(() => {
  void loadProjects().then(() => void loadCases());
});
</script>

<template>
  <div class="ui-page ai-workspace">
    <div class="ai-stage">
      <AiWorkspaceHero
        title="UI Agent"
        subtitle="Playwright GUI Agent：把功能用例编译成浏览器步骤，观察页面并逐步或全量执行。"
        badge="AI · GUI AGENT"
        :status-label="busyAction === 'agent' ? 'Agent 执行中' : `绑定用例 ${cases.length} 条`"
        :status-tone="busyAction === 'agent' ? 'busy' : 'online'"
      >
        <template #extra>
          <a-space>
            <a-select
              v-model="projectId"
              style="width: 200px"
              placeholder="选择项目"
              allow-search
              :disabled="!projects.length"
            >
              <a-option v-for="item in projects" :key="item.id" :value="item.id">{{ item.name }}</a-option>
            </a-select>
            <a-button type="primary" class="ai-action-btn" :loading="busyAction === 'agent'" @click="runAgent">
              GUI Agent 执行
            </a-button>
            <a-button type="outline" :disabled="!projectId" @click="() => void loadCases()">刷新</a-button>
          </a-space>
        </template>
      </AiWorkspaceHero>

      <AiPipelineBar current="ui" :handoff="pipelineHandoff" />
    </div>

    <AiBusyBanner :active="busyAction === 'agent' || busyAction === 'generate'" title="Playwright GUI Agent 工作中" />

    <a-card title="Agent 工作模式" class="ui-card ai-panel ai-guide-rail">
      <div class="ai-guide-rail__row">
        <div class="ai-guide ai-guide--horizontal">
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">01</span>
            <div>
              <div class="ai-guide-step__title">从用例生成</div>
              <div class="ai-guide-step__desc">把功能步骤编译为 Playwright DSL（goto / click / fill / assert）</div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">02</span>
            <div>
              <div class="ai-guide-step__title">观察与预览</div>
              <div class="ai-guide-step__desc">核对选择器、URL 与断言，必要时改 JSON 后再跑</div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">03</span>
            <div>
              <div class="ai-guide-step__title">GUI Agent 执行</div>
              <div class="ai-guide-step__desc">Chromium 逐步操作页面，记录截图与可见文本轨迹</div>
            </div>
          </div>
        </div>
        <div class="ai-next-hint">
          <p class="ai-next-hint__title">Next · 流水提示</p>
          <p class="ai-next-hint__desc">UI 跑通后可带 case_id 进入接口 Agent，生成并执行 API DSL。</p>
        </div>
      </div>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="6">
        <a-card title="绑定用例" size="small" class="ai-panel">
          <div class="ai-chip-rail">
            <span class="ai-chip">Playwright</span>
            <span class="ai-chip">{{ cases.length }}</span>
          </div>
          <div v-if="!cases.length" class="ai-empty">
            <p class="ai-empty__title">暂无功能用例</p>
            <p class="ai-empty__desc">请先在「01 需求 Agent」生成或转入用例，再交给 GUI Agent。</p>
            <a-button type="primary" class="ai-action-btn" size="small" @click="goRequirements">去需求 Agent</a-button>
          </div>
          <a-list v-else size="small" :bordered="false">
            <a-list-item
              v-for="item in cases"
              :key="item.id"
              :class="{ 'ai-session-active': item.id === selectedCaseId }"
              style="cursor: pointer"
              @click="selectCase(item.id)"
            >
              <a-list-item-meta :title="item.title || `用例 #${item.id}`" :description="`#${item.id}`" />
            </a-list-item>
          </a-list>
        </a-card>
      </a-col>
      <a-col :span="18">
        <a-card title="Playwright GUI Agent" size="small" class="ai-panel ai-panel--accent">
          <div class="ai-chip-rail">
            <span class="ai-chip ai-chip--live">Chromium</span>
            <span class="ai-chip">Step Engine</span>
            <span v-if="selectedCase" class="ai-chip">绑定：{{ selectedCase.title || `#${selectedCase.id}` }}</span>
          </div>
          <a-alert type="info" show-icon style="margin-bottom: 12px">
            选择左侧用例 →「从用例生成」编译 DSL →「预览步骤」核对 →「GUI Agent 执行」让 Playwright 操作真实页面。
          </a-alert>

          <div class="ui-toolbar">
            <a-button
              :disabled="!selectedCaseId || !canCaseWrite"
              :loading="busyAction === 'generate'"
              @click="generateFromCase"
            >
              从用例生成
            </a-button>
            <a-button :loading="busyAction === 'preview'" type="outline" @click="runPreview">预览步骤</a-button>
            <div class="ui-step-picker">
              <span class="ui-step-picker__label">步骤序号</span>
              <a-input-number
                v-model="stepIndex"
                :min="0"
                :max="stepCount > 0 ? maxStepIndex : 999"
                :precision="0"
                :style="{ width: '88px' }"
              />
              <span class="ui-step-picker__hint">
                从 0 开始{{ stepCount ? `，当前共 ${stepCount} 步` : "（先生成或预览）" }}
              </span>
            </div>
            <a-button type="outline" :loading="busyAction === 'step'" :disabled="!canCaseWrite" @click="runStep">
              单步执行
            </a-button>
            <a-button
              type="primary"
              class="ai-action-btn"
              :loading="busyAction === 'agent'"
              :disabled="!canCaseWrite"
              @click="runAgent"
            >
              GUI Agent 执行
            </a-button>
            <a-button
              type="outline"
              :disabled="!selectedCaseId || !canCaseWrite"
              :loading="busyAction === 'save'"
              @click="saveScript"
            >
              保存脚本
            </a-button>
            <a-button type="text" @click="goInterface">继续接口 Agent</a-button>
          </div>

          <a-textarea
            v-model="scriptJson"
            :rows="14"
            class="ui-script-editor"
            placeholder='{ "version":"1", "base_url":"http://127.0.0.1:8088", "steps":[{"name":"打开首页","action":"goto","url":"/"}] }'
          />

          <div v-if="preview" class="ui-result-block">
            <div class="ai-section-title">步骤预览</div>
            <a-table
              v-if="Array.isArray(preview.steps) && preview.steps.length"
              size="small"
              row-key="index"
              :pagination="false"
              :data="preview.steps"
              :columns="[
                { title: '序号', dataIndex: 'index', width: 72 },
                { title: '名称', dataIndex: 'name', width: 140 },
                { title: '动作', dataIndex: 'action', width: 110 },
                { title: '选择器 / URL', slotName: 'target', ellipsis: true },
              ]"
            >
              <template #target="{ record }">
                {{ record.selector || record.url || record.value || "—" }}
              </template>
            </a-table>
          </div>

          <div v-if="agentTraces.length" class="ui-result-block">
            <div class="ai-section-title">GUI Agent 轨迹（观察 → 操作）</div>
            <a-table
              size="small"
              row-key="index"
              :pagination="false"
              :data="agentTraces"
              :columns="[
                { title: '序号', dataIndex: 'index', width: 72 },
                { title: '动作', dataIndex: 'action', width: 110 },
                { title: '定位', dataIndex: 'locator', ellipsis: true },
                { title: '结果', slotName: 'ok', width: 80 },
                { title: '页面', dataIndex: 'title', ellipsis: true },
              ]"
            >
              <template #ok="{ record }">
                <a-tag :color="record.ok ? 'green' : 'red'">{{ record.ok ? "ok" : "fail" }}</a-tag>
              </template>
            </a-table>
            <div class="ui-trace-shots">
              <figure v-for="row in agentTraces" :key="'shot-' + row.index" class="ui-trace-shot">
                <img
                  v-if="row.screenshot_data_url"
                  :src="String(row.screenshot_data_url)"
                  :alt="`step ${row.index}`"
                />
                <figcaption>#{{ row.index }} {{ row.action }} {{ row.goal || row.name || "" }}</figcaption>
              </figure>
            </div>
          </div>

          <div v-if="stepResult" class="ui-result-block">
            <div class="ai-section-title">单步执行结果</div>
            <pre class="ai-payload" style="max-height: 180px">{{ JSON.stringify(stepResult, null, 2) }}</pre>
          </div>
          <div v-if="agentResult" class="ui-result-block">
            <div class="ai-section-title">Agent 执行结果</div>
            <pre class="ai-payload" style="max-height: 220px">{{ JSON.stringify(agentResult, null, 2) }}</pre>
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.ui-card :deep(.arco-card-body) {
  padding-top: 12px;
}

.ui-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.ui-step-picker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 10px;
  border: 1px solid rgba(14, 165, 233, 0.28);
  background: rgba(240, 249, 255, 0.9);
}

.ui-step-picker__label {
  font-size: 12px;
  font-weight: 650;
  color: #0369a1;
  white-space: nowrap;
}

.ui-step-picker__hint {
  font-size: 12px;
  color: var(--color-text-3);
  white-space: nowrap;
}

.ui-result-block {
  margin-top: 12px;
}

.ui-trace-shots {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.ui-trace-shot {
  margin: 0;
  border: 1px solid rgba(14, 165, 233, 0.25);
  border-radius: 10px;
  overflow: hidden;
  background: #0b1220;
}

.ui-trace-shot img {
  display: block;
  width: 100%;
  height: 110px;
  object-fit: cover;
  object-position: top;
}

.ui-trace-shot figcaption {
  padding: 6px 8px;
  font-size: 12px;
  color: var(--color-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ui-script-editor :deep(textarea),
.ui-script-editor {
  font-family: "JetBrains Mono", ui-monospace, Menlo, Monaco, Consolas, monospace !important;
  font-size: 12px;
  line-height: 1.55;
  color: #e2e8f0 !important;
  background:
    radial-gradient(ellipse at top left, rgba(14, 165, 233, 0.18), transparent 42%),
    #0b1220 !important;
  border: 1px solid rgba(56, 189, 248, 0.2) !important;
  border-radius: 12px !important;
}
</style>
