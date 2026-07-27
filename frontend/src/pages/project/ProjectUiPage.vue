<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { casesApi } from "../../api/cases";
import { previewUiScriptLocally, uiAutomationApi } from "../../api/uiAutomation";
import { useProjectScope } from "../../composables/useProjectScope";
import { usePlatformStore } from "../../state/platform";
import type { FunctionalCase } from "../../types";

const store = usePlatformStore();
const router = useRouter();
const { projectId } = useProjectScope();

const cases = ref<FunctionalCase[]>([]);
const selectedCaseId = ref<number | null>(null);
const defaultUiBase = () =>
  typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:5174";

const scriptJson = ref(
  `{\n  "version": "1",\n  "base_url": "${typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:5174"}",\n  "steps": []\n}`,
);
const preview = ref<Record<string, unknown> | null>(null);
const stepResult = ref<Record<string, unknown> | null>(null);
const stepIndex = ref(0);
const busyAction = ref<"" | "generate" | "preview" | "step" | "save">("");

const selectedCase = computed(
  () => cases.value.find((row) => row.id === selectedCaseId.value) ?? null,
);

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

watch(stepCount, (count) => {
  if (count <= 0) {
    stepIndex.value = 0;
    return;
  }
  if (stepIndex.value > count - 1) {
    stepIndex.value = count - 1;
  }
});

const parseScriptJson = (): unknown | null => {
  try {
    return JSON.parse(scriptJson.value);
  } catch {
    Message.warning("脚本 JSON 格式无效，请检查后再试");
    return null;
  }
};

const loadCases = () =>
  store.wrap(async () => {
    cases.value = await casesApi.listCases(projectId.value);
    if (!selectedCaseId.value && cases.value.length) {
      selectedCaseId.value = cases.value[0].id;
      await loadScript();
    }
  });

const selectCase = (caseId: number) => {
  selectedCaseId.value = caseId;
  preview.value = null;
  stepResult.value = null;
  void store.wrap(loadScript);
};

const loadScript = async () => {
  if (!selectedCaseId.value) return;
  const data = await uiAutomationApi.getCaseScript(projectId.value, selectedCaseId.value);
  scriptJson.value = JSON.stringify(
    data.ui_script ?? {
      version: "1",
      base_url: defaultUiBase(),
      steps: [],
    },
    null,
    2,
  );
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
  let value = "";
  if (uiScript && typeof uiScript === "object" && "base_url" in uiScript) {
    const raw = (uiScript as { base_url?: unknown }).base_url;
    if (typeof raw === "string" && raw.trim()) value = raw.trim().replace(/\/$/, "");
  }
  if (!value) return pageOrigin;
  // Prefer the page the user is actually viewing when DSL still points at a dead Vite port.
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
  const next = { ...(parsed as Record<string, unknown>), base_url: baseUrl };
  scriptJson.value = JSON.stringify(next, null, 2);
};

const runPreview = () => {
  const uiScript = parseScriptJson();
  if (!uiScript) return;
  busyAction.value = "preview";
  void store
    .wrap(async () => {
      const baseUrl = scriptBaseUrl(uiScript);
      const payload = withResolvedBase(uiScript, baseUrl);
      syncEditorBaseUrl(baseUrl);
      try {
        preview.value = await uiAutomationApi.preview(projectId.value, payload, baseUrl);
      } catch (error) {
        // 后端不可达时仍提供本地结构预览，保证「预览步骤」可用
        preview.value = previewUiScriptLocally(payload, baseUrl);
        const msg = error instanceof Error ? error.message : String(error);
        Message.warning(`后端预览失败，已使用本地解析：${msg}`);
      }
      const count = Array.isArray(preview.value?.steps) ? preview.value.steps.length : 0;
      if (count) {
        Message.success(`已解析 ${count} 个步骤`);
      } else {
        Message.warning("脚本暂无步骤，请先「从用例生成」或编辑 steps");
      }
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const runStep = () => {
  if (stepCount.value <= 0) {
    Message.warning("当前脚本没有可执行步骤，请先「预览步骤」或补充 steps");
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
      stepResult.value = await uiAutomationApi.executeStep(projectId.value, payload, index, baseUrl);
      const status = String(stepResult.value?.status || "");
      if (status === "skipped") {
        const reason =
          (stepResult.value?.detail as { reason?: string } | undefined)?.reason ||
          "步骤已跳过";
        Message.warning(`${reason}（详见下方结果）`);
        return;
      }
      if (status === "failed" || status === "error") {
        const detailReason = (stepResult.value?.detail as { reason?: string } | undefined)?.reason;
        Message.error(
          detailReason || `步骤 #${index} 执行失败：${String(stepResult.value?.stderr || "")}`,
        );
        return;
      }
      Message.success(`已执行到步骤 #${index}（含前置步骤），目标 ${baseUrl}`);
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const saveScript = () => {
  if (!selectedCaseId.value) {
    Message.warning("请先选择左侧用例");
    return;
  }
  const uiScript = parseScriptJson();
  if (!uiScript) return;
  busyAction.value = "save";
  void store
    .wrap(async () => {
      await uiAutomationApi.updateCaseScript(projectId.value, selectedCaseId.value!, uiScript);
      Message.success("UI 脚本已保存到当前用例");
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const generateFromCase = () => {
  if (!selectedCaseId.value) {
    Message.warning("请先选择左侧用例");
    return;
  }
  busyAction.value = "generate";
  void store
    .wrap(async () => {
      const data = await uiAutomationApi.generateFromCase(projectId.value, selectedCaseId.value!);
      const baseUrl = scriptBaseUrl(data.ui_script) || defaultUiBase();
      const payload = withResolvedBase(data.ui_script, baseUrl);
      scriptJson.value = JSON.stringify(payload, null, 2);
      try {
        preview.value = await uiAutomationApi.preview(projectId.value, payload, baseUrl);
      } catch {
        preview.value = previewUiScriptLocally(payload, baseUrl);
      }
      stepResult.value = null;
      const count = Array.isArray(preview.value?.steps) ? preview.value.steps.length : 0;
      Message.success(`已从用例生成 UI DSL（${count} 步），目标 ${baseUrl}`);
    })
    .finally(() => {
      busyAction.value = "";
    });
};

const goCases = () => {
  void router.push({ name: "project-cases", params: { id: projectId.value } });
};

onMounted(() => void loadCases());
</script>

<template>
  <a-row :gutter="16">
    <a-col :span="6">
      <a-card title="绑定用例" size="small" class="ai-panel">
        <div class="ai-chip-rail">
          <span class="ai-chip">UI Cases</span>
          <span class="ai-chip">{{ cases.length }}</span>
        </div>
        <div v-if="!cases.length" class="ai-empty">
          <p class="ai-empty__title">暂无功能用例</p>
          <p class="ai-empty__desc">UI 脚本需绑定到功能用例。请先在「01 用例」生成或导入用例。</p>
          <a-button type="primary" class="ai-action-btn" size="small" @click="goCases">去用例管理</a-button>
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
      <a-card title="UI DSL（Playwright）" size="small" class="ai-panel ai-panel--accent">
        <div class="ai-chip-rail">
          <span class="ai-chip ai-chip--live">Playwright</span>
          <span class="ai-chip">Step Engine</span>
          <span v-if="selectedCase" class="ai-chip">绑定：{{ selectedCase.title || `#${selectedCase.id}` }}</span>
        </div>
        <a-alert type="info" show-icon style="margin-bottom: 12px">
          这里编排浏览器自动化脚本：先选左侧用例 →「从用例生成」或手写 JSON →「预览步骤」核对 →
          用「步骤序号」指定要跑的一步再「单步执行」。
        </a-alert>

        <div class="ui-toolbar">
          <a-button
            :disabled="!selectedCaseId"
            :loading="busyAction === 'generate'"
            @click="generateFromCase"
          >
            从用例生成
          </a-button>
          <a-button :loading="busyAction === 'preview'" type="outline" @click="runPreview">
            预览步骤
          </a-button>
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
              从 0 开始{{ stepCount ? `，当前共 ${stepCount} 步` : "（先预览或填写 steps）" }}
            </span>
          </div>
          <a-button
            type="primary"
            class="ai-action-btn"
            :loading="busyAction === 'step'"
            @click="runStep"
          >
            单步执行
          </a-button>
          <a-button
            type="outline"
            :disabled="!selectedCaseId"
            :loading="busyAction === 'save'"
            @click="saveScript"
          >
            保存脚本
          </a-button>
        </div>

        <a-textarea
          v-model="scriptJson"
          :rows="16"
          class="ui-script-editor"
          placeholder='请输入 UI DSL JSON，例如：{ "version":"1", "base_url":"http://127.0.0.1:5174", "steps":[{"name":"打开首页","action":"goto","url":"/"}] }'
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
            style="margin-bottom: 8px"
          >
            <template #target="{ record }">
              {{ record.selector || record.url || record.value || "—" }}
            </template>
          </a-table>
          <pre class="ai-payload" style="max-height: 180px">{{ JSON.stringify(preview, null, 2) }}</pre>
        </div>
        <div v-if="stepResult" class="ui-result-block">
          <div class="ai-section-title">单步执行结果</div>
          <pre class="ai-payload" style="max-height: 180px">{{ JSON.stringify(stepResult, null, 2) }}</pre>
        </div>
      </a-card>
    </a-col>
  </a-row>
</template>

<style scoped>
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
