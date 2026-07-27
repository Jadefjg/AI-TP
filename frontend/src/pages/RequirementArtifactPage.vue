<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { aiApi } from "../api/ai";
import { casesApi } from "../api/cases";
import AiBusyBanner from "../components/ai/AiBusyBanner.vue";
import AiPipelineBar from "../components/ai/AiPipelineBar.vue";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { projectsApi } from "../api/projects";
import {
  buildPipelineQuery,
  parsePipelineQuery,
  pipelineRouteName,
  recalledPipelineProjectId,
  rememberPipelineProjectId,
  type AiPipelineStepKey,
} from "../constants/aiPipeline";
import { listTablePagination } from "../constants/listPagination";
import {
  formatCaseInfoForApi,
  REQUIREMENT_ARTIFACT_MODULES,
  type RequirementArtifactModule,
} from "../constants/requirementArtifactModules";
import {
  clipRequirementPreview,
  reviewSourceLabel,
  type RequirementReviewRow,
} from "../constants/requirementReview";
import { usePlatformStore } from "../state/platform";
import type { AiArtifact, FunctionalCase, Project } from "../types";

const props = defineProps<{
  moduleKey: RequirementArtifactModule;
}>();

const store = usePlatformStore();
const router = useRouter();
const route = useRoute();

const config = computed(() => REQUIREMENT_ARTIFACT_MODULES[props.moduleKey]);

const pipelineCurrent = computed<AiPipelineStepKey>(() => {
  if (props.moduleKey === "api_automation") return "interface";
  if (props.moduleKey === "perf_plan") return "perf";
  return "security";
});

const heroBadge = computed(() => {
  if (props.moduleKey === "api_automation") return "AI · API DSL";
  if (props.moduleKey === "perf_plan") return "AI · PERF";
  return "AI · SECURITY";
});

const projects = ref<Project[]>([]);
const projectId = ref<number | null>(null);
const reviews = ref<RequirementReviewRow[]>([]);
const selectedReviewId = ref<number | null>(null);
const artifacts = ref<AiArtifact[]>([]);
const functionalCases = ref<FunctionalCase[]>([]);
const selectedCaseId = ref<number | null>(null);
const apiArtifacts = ref<AiArtifact[]>([]);
const selectedApiArtifactId = ref<number | null>(null);
const useApiArtifactContext = ref(true);
const generating = ref(false);
const executingId = ref<number | null>(null);
const requirementOverride = ref("");
const latestPayload = ref<Record<string, unknown> | unknown[] | null>(null);
const latestExecResult = ref<Record<string, unknown> | null>(null);
const tablePagination = listTablePagination(10);

const baseUrl = ref("http://127.0.0.1:8001");
const targetUrl = ref("http://127.0.0.1:8001/system/health");
const scanMethod = ref("GET");
const paramName = ref("q");
const paramValue = ref("test");
const securityEngine = ref("builtin");
const perfDistributed = ref(true);

const securityJobs = ref<Array<Record<string, unknown>>>([]);
const perfJobs = ref<Array<Record<string, unknown>>>([]);

const canAiRead = computed(() => store.hasPermission("ai.read"));
const canAiExecute = computed(() => store.hasPermission("ai.execute"));

const selectedReview = computed(
  () => reviews.value.find((row) => row.id === selectedReviewId.value) ?? null,
);

const selectedCase = computed(
  () => functionalCases.value.find((row) => row.id === selectedCaseId.value) ?? null,
);

const selectedApiArtifact = computed(
  () => apiArtifacts.value.find((row) => row.id === selectedApiArtifactId.value) ?? null,
);

const requirementText = computed(() => {
  const override = requirementOverride.value.trim();
  if (override) return override;
  return (selectedReview.value?.requirement_text || "").trim();
});

const pipelineHandoff = computed(() => ({
  projectId: projectId.value,
  reviewId: selectedReviewId.value,
  caseId: selectedCaseId.value,
  artifactId: artifacts.value[0]?.id ?? null,
}));

const apiDocExtra = computed(() => {
  if (!useApiArtifactContext.value || props.moduleKey === "api_automation") return "";
  const payload = selectedApiArtifact.value?.payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
  const script = (payload as Record<string, unknown>).script_content;
  return typeof script === "string" ? script : JSON.stringify(payload, null, 2);
});

const executeLabel = computed(() => {
  if (props.moduleKey === "api_automation") return "执行 DSL";
  if (props.moduleKey === "perf_plan") return "下发 k6";
  return "发起扫描";
});

const busyTitle = computed(() => {
  if (generating.value) return `AI 正在生成${config.value.title.replace("管理", "")}`;
  if (executingId.value) return `${executeLabel.value}进行中`;
  return "AI 工作中";
});

const busyActive = computed(() => generating.value || executingId.value !== null);

const artifactColumns = computed(() => [
  { title: "ID", dataIndex: "id", width: 72, align: "center" as const },
  { title: "标题", dataIndex: "title", ellipsis: true, tooltip: true, minWidth: 180 },
  { title: "模型", dataIndex: "model_name", width: 140, ellipsis: true },
  { title: "时间", slotName: "createdAt", width: 168 },
  {
    title: "操作",
    slotName: "actions",
    width: canAiExecute.value ? 220 : 100,
    align: "center" as const,
    fixed: "right" as const,
  },
]);

const reviewColumns = [
  { title: "ID", dataIndex: "id", width: 72, align: "center" as const },
  { title: "来源", slotName: "source", ellipsis: true, tooltip: true, minWidth: 160 },
  { title: "需求摘要", slotName: "preview", ellipsis: true, tooltip: true, minWidth: 220 },
  { title: "模型", dataIndex: "model_name", width: 130, ellipsis: true },
  { title: "时间", slotName: "createdAt", width: 168 },
];

const formatDateTime = (value: string | null | undefined) => {
  if (!value) return "—";
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ").slice(0, 19);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
};

const ensureProject = () => {
  if (!projectId.value) {
    Message.warning("请先选择项目");
    return false;
  }
  return true;
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

const loadReviews = () =>
  store.runBackground(async () => {
    if (!canAiRead.value || !projectId.value) {
      reviews.value = [];
      selectedReviewId.value = null;
      requirementOverride.value = "";
      return;
    }
    reviews.value = await aiApi.listRequirementReviews(projectId.value);
    const wanted = parsePipelineQuery(route.query as Record<string, unknown>).reviewId;
    if (wanted && reviews.value.some((row) => row.id === wanted)) {
      selectedReviewId.value = wanted;
    } else if (!reviews.value.some((row) => row.id === selectedReviewId.value)) {
      selectedReviewId.value = reviews.value[0]?.id ?? null;
    }
    syncRequirementFromReview();
  });

const loadFunctionalCases = async () => {
  if (props.moduleKey !== "api_automation" || !projectId.value) {
    functionalCases.value = [];
    selectedCaseId.value = null;
    return;
  }
  try {
    functionalCases.value = await casesApi.listCases(projectId.value);
  } catch {
    functionalCases.value = [];
  }
  const wanted = parsePipelineQuery(route.query as Record<string, unknown>).caseId;
  if (wanted && functionalCases.value.some((row) => row.id === wanted)) {
    selectedCaseId.value = wanted;
  } else if (!functionalCases.value.some((row) => row.id === selectedCaseId.value)) {
    selectedCaseId.value = functionalCases.value[0]?.id ?? null;
  }
};

const loadApiArtifacts = async () => {
  if (props.moduleKey === "api_automation" || !canAiRead.value || !projectId.value) {
    apiArtifacts.value = [];
    selectedApiArtifactId.value = null;
    return;
  }
  apiArtifacts.value = await aiApi.listAiArtifacts(projectId.value, "api_automation");
  const wanted = parsePipelineQuery(route.query as Record<string, unknown>).artifactId;
  if (wanted && apiArtifacts.value.some((row) => row.id === wanted)) {
    selectedApiArtifactId.value = wanted;
  } else if (!apiArtifacts.value.some((row) => row.id === selectedApiArtifactId.value)) {
    selectedApiArtifactId.value = apiArtifacts.value[0]?.id ?? null;
  }
};

const loadArtifacts = async () => {
  if (!canAiRead.value || !projectId.value) {
    artifacts.value = [];
    return;
  }
  artifacts.value = await aiApi.listAiArtifacts(projectId.value, props.moduleKey);
};

const loadJobs = async () => {
  if (!canAiRead.value || !projectId.value) {
    securityJobs.value = [];
    perfJobs.value = [];
    return;
  }
  if (props.moduleKey === "security_scan") {
    securityJobs.value = await aiApi.listSecurityScanJobs(projectId.value);
  } else if (props.moduleKey === "perf_plan") {
    perfJobs.value = await aiApi.listPerfK6Jobs(projectId.value);
  }
};

const syncRequirementFromReview = () => {
  const text = (selectedReview.value?.requirement_text || "").trim();
  if (text) {
    requirementOverride.value = text;
  }
};

const fillFromReview = () => {
  const text = (selectedReview.value?.requirement_text || "").trim();
  if (!text) {
    Message.warning("当前评审记录没有需求正文，请先在需求管理中重新分析");
    return;
  }
  requirementOverride.value = text;
  Message.success("已填入需求正文");
};

const generateFromRequirement = () => {
  if (!ensureProject()) return;
  if (!canAiExecute.value) {
    Message.warning("缺少 ai.execute 权限");
    return;
  }
  const text = requirementText.value;
  if (text.length < 10) {
    Message.warning("请选择需求评审记录，或粘贴至少 10 个字符的需求正文");
    return;
  }
  generating.value = true;
  void store
    .wrap(async () => {
      const result = await config.value.generate(projectId.value!, text, {
        caseId: props.moduleKey === "api_automation" ? selectedCaseId.value : null,
        caseInfo:
          props.moduleKey === "api_automation" && selectedCase.value
            ? formatCaseInfoForApi(selectedCase.value)
            : null,
        apiDocExtra: apiDocExtra.value || null,
      });
      latestPayload.value = result.payload;
      if (!result.persisted_ids?.length) {
        Message.warning("生成完成但未入库，请检查权限或后端日志");
      }
      await loadArtifacts();
      Message.success(
        `${config.value.title}生成完成（模型 ${result.model}${
          result.persisted_ids?.length ? ` · 产物 #${result.persisted_ids.join(",")}` : ""
        }）`,
      );
      const nextKey = config.value.nextStepKey;
      if (nextKey && result.persisted_ids?.length) {
        Modal.confirm({
          title: "继续下一阶段？",
          content:
            nextKey === "perf"
              ? "接口脚本已入库。是否带着当前上下文进入性能管理？"
              : "压测方案已入库。是否带着当前上下文进入安全管理？",
          okText: nextKey === "perf" ? "去性能管理" : "去安全管理",
          cancelText: "留在本页",
          onOk: () => {
            rememberPipelineProjectId(projectId.value);
            return router.push({
              name: pipelineRouteName(nextKey),
              query: buildPipelineQuery({
                projectId: projectId.value,
                reviewId: selectedReviewId.value,
                caseId: selectedCaseId.value,
                artifactId: result.persisted_ids[0],
              }),
            });
          },
        });
      }
    })
    .finally(() => {
      generating.value = false;
    });
};
const viewArtifact = (row: AiArtifact) => {
  latestPayload.value = row.payload;
};

const executeArtifact = (row: AiArtifact) => {
  if (!ensureProject()) return;
  if (!canAiExecute.value) {
    Message.warning("缺少 ai.execute 权限");
    return;
  }
  executingId.value = row.id;
  void store
    .wrap(async () => {
      let result: Record<string, unknown>;
      if (props.moduleKey === "api_automation") {
        result = await aiApi.executeApiArtifact(projectId.value!, row.id, {
          baseUrl: baseUrl.value,
        });
      } else if (props.moduleKey === "perf_plan") {
        result = await aiApi.dispatchPerfArtifact(
          projectId.value!,
          row.id,
          baseUrl.value,
          perfDistributed.value,
        );
      } else {
        if (!targetUrl.value.trim()) {
          Message.warning("请填写扫描目标 URL");
          return;
        }
        result = await aiApi.dispatchSecurityArtifact(projectId.value!, row.id, {
          target_url: targetUrl.value.trim(),
          method: scanMethod.value,
          query_params: { [paramName.value || "q"]: paramValue.value || "test" },
          engine: securityEngine.value,
        });
      }
      latestExecResult.value = result;
      latestPayload.value = row.payload;
      const status = String(result.status || "");
      const reason =
        typeof result.reason === "string"
          ? result.reason
          : typeof result.detail === "object" && result.detail && "reason" in (result.detail as object)
            ? String((result.detail as { reason?: unknown }).reason || "")
            : typeof result.detail === "string"
              ? result.detail
              : "";
      if (status === "skipped") {
        Message.warning(`已跳过：${reason || "工具不可用（将保留任务记录）"}`);
      } else {
        Message.success(`${executeLabel.value}完成（状态 ${status || "ok"}）`);
      }
      await loadJobs();
    })
    .finally(() => {
      executingId.value = null;
    });
};

const goRequirements = () => {
  void router.push({
    name: "requirements",
    query: buildPipelineQuery({ projectId: projectId.value, reviewId: selectedReviewId.value }),
  });
};

const goProjectAi = () => {
  if (!projectId.value) return;
  void router.push({ name: "project-ai", params: { id: String(projectId.value) } });
};

const refreshAll = () => {
  void store.wrap(async () => {
    await loadReviews();
    await loadArtifacts();
    await loadJobs();
    await loadFunctionalCases();
    await loadApiArtifacts();
  });
};

const selectReview = (record: RequirementReviewRow) => {
  selectedReviewId.value = record.id;
  syncRequirementFromReview();
};

watch(
  () => [projectId.value, props.moduleKey, route.name, route.query] as const,
  () => {
    rememberPipelineProjectId(projectId.value);
    requirementOverride.value = "";
    latestPayload.value = null;
    latestExecResult.value = null;
    void loadReviews();
    void store.runBackground(async () => {
      await loadArtifacts();
      await loadJobs();
      await loadFunctionalCases();
      await loadApiArtifacts();
    });
  },
);

watch(selectedReviewId, () => {
  syncRequirementFromReview();
});

onMounted(() => {
  void loadProjects().then(() => {
    void loadReviews();
    void store.runBackground(async () => {
      await loadArtifacts();
      await loadJobs();
      await loadFunctionalCases();
      await loadApiArtifacts();
    });
  });
});
</script>

<template>
  <div class="artifact-page ai-workspace">
    <AiWorkspaceHero
      :title="config.title"
      :subtitle="config.subtitle"
      :badge="heroBadge"
      :status-label="busyActive ? 'Agent 工作中' : `产物 ${artifacts.length} 条`"
      :status-tone="busyActive ? 'busy' : 'online'"
    >
      <template #extra>
        <a-space wrap>
          <a-select
            v-model="projectId"
            style="width: 200px"
            placeholder="选择项目"
            allow-search
            :disabled="!projects.length"
          >
            <a-option v-for="item in projects" :key="item.id" :value="item.id">{{ item.name }}</a-option>
          </a-select>
          <a-button :disabled="!projectId" @click="goRequirements">去需求</a-button>
          <a-button :disabled="!projectId" @click="goProjectAi">项目 AI</a-button>
          <a-button
            v-if="moduleKey === 'perf_plan'"
            @click="() => router.push({ name: 'perf-management', query: buildPipelineQuery({ projectId }) })"
          >
            性能测试
          </a-button>
          <a-button type="outline" :loading="store.loading.value" :disabled="!projectId" @click="refreshAll">
            刷新
          </a-button>
        </a-space>
      </template>
    </AiWorkspaceHero>

    <AiPipelineBar :current="pipelineCurrent" :handoff="pipelineHandoff" />
    <AiBusyBanner :active="busyActive" :title="busyTitle" />

    <a-card title="生成说明" class="artifact-card ai-panel ai-guide-rail">
      <div class="artifact-tips artifact-tips--horizontal">
        <div v-for="tip in config.tips" :key="tip.label" class="artifact-tip">
          <div class="artifact-tip__title">{{ tip.label }}</div>
          <div class="artifact-tip__desc">{{ tip.text }}</div>
        </div>
      </div>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="24">
        <a-card :title="`从需求生成${config.title.replace('管理', '')}`" class="artifact-card ai-panel ai-panel--accent">
          <a-typography-text type="secondary">
            选择需求评审，把正文交给 AI 生成产物并自动入库；生成后可直接在本页执行。
          </a-typography-text>

          <div class="artifact-field">
            <div class="artifact-field__label">需求评审来源</div>
            <div v-if="!reviews.length" class="ai-empty">
              <p class="ai-empty__title">还没有评审可用来生成</p>
              <p class="ai-empty__desc">先完成需求分析，再回来让 Agent 产出这一层的测试产物。</p>
              <a-button type="outline" size="small" @click="goRequirements">去需求分析</a-button>
            </div>
            <a-table
              v-else
              :data="reviews"
              :columns="reviewColumns"
              row-key="id"
              size="small"
              :pagination="{ pageSize: 5, showTotal: true }"
              :row-class="(record: RequirementReviewRow) => (record.id === selectedReviewId ? 'ai-row--active' : '')"
              :scroll="{ x: 700 }"
              @row-click="selectReview"
            >
              <template #source="{ record }">
                <span>{{ reviewSourceLabel(record) }}</span>
                <a-tag v-if="record.source_format" size="small" style="margin-left: 6px">
                  {{ record.source_format }}
                </a-tag>
              </template>
              <template #preview="{ record }">
                {{ clipRequirementPreview(record.requirement_text) }}
              </template>
              <template #createdAt="{ record }">
                {{ formatDateTime(record.created_at) }}
              </template>
            </a-table>
            <a-button
              size="small"
              style="margin-top: 8px"
              :disabled="!selectedReview"
              @click="fillFromReview"
            >
              填入选中需求正文
            </a-button>
          </div>

          <div class="artifact-field">
            <div class="artifact-field__label">需求正文（生成输入）</div>
            <a-textarea
              v-model="requirementOverride"
              :auto-size="{ minRows: 6, maxRows: 14 }"
              placeholder="自动使用选中评审的需求正文；也可在此粘贴/编辑后再生成"
            />
            <a-typography-paragraph type="secondary" style="margin-top: 8px; margin-bottom: 0">
              当前有效字数：{{ requirementText.length }}
              <template v-if="selectedReview"> · 已选评审 #{{ selectedReview.id }}</template>
            </a-typography-paragraph>

            <div v-if="moduleKey === 'api_automation'" class="artifact-field" style="margin-top: 12px">
              <div class="artifact-field__label">绑定功能用例（可选，推荐）</div>
              <a-select
                v-model="selectedCaseId"
                allow-clear
                allow-search
                placeholder="选择用例后将带 case_id 生成接口脚本"
                :disabled="!functionalCases.length"
              >
                <a-option v-for="item in functionalCases" :key="item.id" :value="item.id">
                  #{{ item.id }} {{ item.title }}
                </a-option>
              </a-select>
              <a-typography-paragraph type="secondary" style="margin-top: 6px; margin-bottom: 0">
                {{
                  selectedCase
                    ? `将使用用例「${selectedCase.title}」作为 case_info`
                    : functionalCases.length
                      ? "未绑定时回退为需求正文"
                      : "暂无用例，可先到用例管理生成"
                }}
              </a-typography-paragraph>
            </div>

            <div v-if="moduleKey !== 'api_automation'" class="artifact-field" style="margin-top: 12px">
              <div class="artifact-field__label">接口产物上下文（可选，推荐）</div>
              <a-space wrap>
                <a-checkbox v-model="useApiArtifactContext">引用接口 DSL</a-checkbox>
                <a-select
                  v-model="selectedApiArtifactId"
                  allow-clear
                  allow-search
                  style="min-width: 260px"
                  placeholder="选择 api_automation 产物"
                  :disabled="!useApiArtifactContext || !apiArtifacts.length"
                >
                  <a-option v-for="item in apiArtifacts" :key="item.id" :value="item.id">
                    #{{ item.id }} {{ item.title || "接口脚本" }}
                  </a-option>
                </a-select>
              </a-space>
              <a-typography-paragraph type="secondary" style="margin-top: 6px; margin-bottom: 0">
                {{
                  apiArtifacts.length
                    ? "会把 DSL 注入到生成上下文，提升压测权重 / 安全入参质量"
                    : "暂无接口产物，可先在接口管理生成 DSL"
                }}
              </a-typography-paragraph>
            </div>

            <div v-if="canAiExecute" class="artifact-field" style="margin-top: 12px">
              <div class="artifact-field__label">执行参数</div>
              <a-space direction="vertical" fill style="width: 100%">
                <template v-if="moduleKey === 'api_automation' || moduleKey === 'perf_plan'">
                  <a-input v-model="baseUrl" placeholder="Base URL，例如 http://127.0.0.1:8001">
                    <template #prefix>Base URL</template>
                  </a-input>
                  <a-checkbox v-if="moduleKey === 'perf_plan'" v-model="perfDistributed">
                    优先分布式调度（有 Worker 时）
                  </a-checkbox>
                </template>
                <template v-else>
                  <a-input v-model="targetUrl" placeholder="扫描目标 URL">
                    <template #prefix>Target</template>
                  </a-input>
                  <a-space wrap>
                    <a-select v-model="scanMethod" style="width: 110px">
                      <a-option value="GET">GET</a-option>
                      <a-option value="POST">POST</a-option>
                      <a-option value="PUT">PUT</a-option>
                      <a-option value="DELETE">DELETE</a-option>
                    </a-select>
                    <a-select v-model="securityEngine" style="width: 140px">
                      <a-option value="builtin">builtin</a-option>
                      <a-option value="nuclei">nuclei</a-option>
                      <a-option value="zap">zap</a-option>
                      <a-option value="combined">combined</a-option>
                    </a-select>
                  </a-space>
                  <a-space>
                    <a-input v-model="paramName" placeholder="参数名" style="width: 120px" />
                    <a-input v-model="paramValue" placeholder="参数值" style="width: 180px" />
                  </a-space>
                </template>
              </a-space>
            </div>
            <a-button
              v-if="canAiExecute"
              type="primary"
              class="ai-action-btn"
              style="margin-top: 12px"
              :loading="generating || store.loading.value"
              @click="generateFromRequirement"
            >
              {{ config.generateLabel }}
            </a-button>
            <a-collapse
              v-if="latestPayload || latestExecResult"
              style="margin-top: 16px"
              :default-active-key="['payload', 'exec']"
            >
              <a-collapse-item v-if="latestPayload" header="最近一次生成结果" key="payload">
                <pre class="ai-payload">{{ JSON.stringify(latestPayload, null, 2) }}</pre>
              </a-collapse-item>
              <a-collapse-item v-if="latestExecResult" header="最近一次执行结果" key="exec">
                <pre class="ai-payload">{{ JSON.stringify(latestExecResult, null, 2) }}</pre>
              </a-collapse-item>
            </a-collapse>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-card :title="`${config.title}产物`" class="artifact-card ai-panel" style="margin-top: 16px">
      <template #extra>
        <a-tag color="arcoblue">共 {{ artifacts.length }} 条</a-tag>
      </template>

      <a-empty v-if="!canAiRead" description="缺少 ai.read 权限" />
      <div v-else-if="!artifacts.length" class="ai-empty">
        <p class="ai-empty__title">还没有生成产物</p>
        <p class="ai-empty__desc">选中需求后点击「{{ config.generateLabel }}」，结果会入库显示在这里。</p>
      </div>
      <a-table
        v-else
        :data="artifacts"
        :columns="artifactColumns"
        row-key="id"
        :loading="store.loading.value"
        :pagination="tablePagination"
        :scroll="{ x: 900 }"
      >
        <template #createdAt="{ record }">
          {{ formatDateTime(record.created_at) }}
        </template>
        <template #actions="{ record }">
          <a-space :size="4">
            <a-button type="text" size="small" @click="viewArtifact(record)">查看</a-button>
            <a-button
              v-if="canAiExecute"
              type="text"
              size="small"
              status="warning"
              :loading="executingId === record.id"
              @click="executeArtifact(record)"
            >
              {{ executeLabel }}
            </a-button>
            <a-button type="text" size="small" @click="goProjectAi">去调试</a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-card
      v-if="moduleKey === 'security_scan' && canAiRead"
      title="安全扫描记录"
      class="artifact-card ai-panel"
      style="margin-top: 16px"
    >
      <template #extra>
        <a-tag>共 {{ securityJobs.length }} 条</a-tag>
      </template>
      <div v-if="!securityJobs.length" class="ai-empty">
        <p class="ai-empty__title">尚无扫描记录</p>
        <p class="ai-empty__desc">生成安全策略后，设置目标 URL，再点「发起扫描」。</p>
      </div>
      <a-list v-else :data="securityJobs" :bordered="false">
        <template #item="{ item }">
          <a-list-item>
            <a-list-item-meta
              :title="`Job #${item.id} · ${item.engine || 'builtin'} · ${item.status}`"
              :description="String(item.target_url || '')"
            />
            <template #actions>
              <a-button
                size="mini"
                @click="aiApi.openSecurityReportHtml(projectId!, Number(item.id))"
              >
                HTML
              </a-button>
              <a-button
                size="mini"
                @click="aiApi.downloadSecurityReportPdf(projectId!, Number(item.id))"
              >
                PDF
              </a-button>
            </template>
            <a-tag :color="item.status === 'failed' ? 'red' : item.status === 'skipped' ? 'orange' : 'green'">
              {{ item.status }}
            </a-tag>
          </a-list-item>
        </template>
      </a-list>
    </a-card>

    <a-card
      v-if="moduleKey === 'perf_plan' && canAiRead"
      title="k6 压测任务"
      class="artifact-card ai-panel"
      style="margin-top: 16px"
    >
      <template #extra>
        <a-tag>共 {{ perfJobs.length }} 条</a-tag>
      </template>
      <div v-if="!perfJobs.length" class="ai-empty">
        <p class="ai-empty__title">尚无压测任务</p>
        <p class="ai-empty__desc">生成方案后填写 Base URL，点击「下发 k6」即可。</p>
      </div>
      <a-table
        v-else
        :data="perfJobs"
        row-key="id"
        size="small"
        :pagination="{ pageSize: 8, showTotal: true }"
        :columns="[
          { title: 'ID', dataIndex: 'id', width: 72 },
          { title: '产物', dataIndex: 'artifact_id', width: 88 },
          { title: '状态', dataIndex: 'status', width: 120 },
          { title: '时间', slotName: 'createdAt', width: 168 },
        ]"
      >
        <template #createdAt="{ record }">
          {{ formatDateTime(String(record.created_at || '')) }}
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<style scoped>
.artifact-card :deep(.arco-card-body) {
  padding-top: 12px;
}

.artifact-field + .artifact-field {
  margin-top: 16px;
}

.artifact-field__label {
  margin-bottom: 8px;
  color: var(--color-text-1);
  font-weight: 500;
}

.artifact-tips {
  display: grid;
  gap: 10px;
}

.artifact-tips--horizontal {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}

.artifact-tips--horizontal .artifact-tip__desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.artifact-tip {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9), #fff);
}

.artifact-tip__title {
  font-size: 13px;
  font-weight: 650;
}

.artifact-tip__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-3);
}
</style>
