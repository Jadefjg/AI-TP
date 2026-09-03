<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { aiApi } from "../api/ai";
import { casesApi } from "../api/cases";
import { projectsApi } from "../api/projects";
import AiBusyBanner from "../components/ai/AiBusyBanner.vue";
import AiAgentReadyAlert from "../components/ai/AiAgentReadyAlert.vue";
import AiPipelineBar from "../components/ai/AiPipelineBar.vue";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import {
  buildPipelineQuery,
  parsePipelineQuery,
  recalledPipelineProjectId,
  rememberPipelineProjectId,
} from "../constants/aiPipeline";
import { listTablePagination } from "../constants/listPagination";
import { formatCaseInfoForApi } from "../constants/requirementArtifactModules";
import { resolveProjectBaseUrl } from "../constants/projectDefaults";
import { usePlatformStore } from "../state/platform";
import type { AiArtifact, FunctionalCase, Project } from "../types";
import { aiSuccessMessage } from "../utils/aiResult";

const store = usePlatformStore();
const router = useRouter();
const route = useRoute();

const projects = ref<Project[]>([]);
const projectId = ref<number | null>(null);
const functionalCases = ref<FunctionalCase[]>([]);
const selectedCaseId = ref<number | null>(null);
const artifacts = ref<AiArtifact[]>([]);
const openapiArtifacts = ref<AiArtifact[]>([]);
const generating = ref(false);
const generatingOpenapi = ref(false);
const executingId = ref<number | null>(null);
const apiNotes = ref("");
const swaggerMode = ref<"discover" | "url" | "manual" | "history">("discover");
const openapiUrl = ref("");
const openapiDraft = ref("");
const selectedOpenapiArtifactId = ref<number | null>(null);
const latestPayload = ref<Record<string, unknown> | unknown[] | null>(null);
const viewVisible = ref(false);
const viewTitle = ref("产物详情");
const viewJsonText = ref("");
const latestOpenApiPayload = ref<Record<string, unknown> | null>(null);
const latestExecResult = ref<Record<string, unknown> | null>(null);
const baseUrl = ref("");
const selectedArtifactId = ref<number | null>(null);
const tablePagination = listTablePagination(10);

const swaggerModes = [
  { key: "discover" as const, label: "读取本地仓库", hint: "扫描项目目录 / 已部署地址，必要时 AI 补全" },
  { key: "url" as const, label: "拉取 JSON", hint: "从 OpenAPI /Swagger URL 拉取文档" },
  { key: "manual" as const, label: "手动录入", hint: "粘贴 OpenAPI JSON 或 YAML" },
  { key: "history" as const, label: "选用历史", hint: "使用本项目已生成的 Swagger 产物" },
];

const canAiRead = computed(() => store.hasPermission("ai.read"));
const canAiExecute = computed(() => store.hasPermission("ai.execute"));

const selectedProject = computed(
  () => projects.value.find((item) => item.id === projectId.value) ?? null,
);

const selectedCase = computed(
  () => functionalCases.value.find((row) => row.id === selectedCaseId.value) ?? null,
);

const sourceLabel = (value: string | null | undefined) => {
  if (value === "remote") return "远程仓库";
  if (value === "deployed") return "已部署";
  if (value === "local") return "本地仓库";
  return value || "—";
};

const sourceTagColor = (value: string | null | undefined) => {
  if (value === "remote") return "arcoblue";
  if (value === "deployed") return "orangered";
  return "green";
};

const locationLabel = computed(() => {
  const source = selectedProject.value?.repo_source;
  if (source === "deployed") return "部署访问地址";
  if (source === "remote") return "Git 仓库";
  return "本地路径";
});

const pipelineHandoff = computed(() => ({
  projectId: projectId.value,
  caseId: selectedCaseId.value,
  artifactId: selectedArtifactId.value ?? artifacts.value[0]?.id ?? null,
}));

const busyActive = computed(
  () => generating.value || generatingOpenapi.value || executingId.value !== null,
);
const busyTitle = computed(() => {
  if (generatingOpenapi.value) {
    if (swaggerMode.value === "url") return "正在拉取 OpenAPI JSON";
    if (swaggerMode.value === "manual") return "正在入库手动录入的 Swagger";
    return "正在根据项目生成 Swagger / OpenAPI";
  }
  if (generating.value) return "AI 正在根据项目生成接口测试";
  if (executingId.value) return "DSL 执行中";
  return "AI 工作中";
});

const extractOpenApiPayload = (payload: unknown): Record<string, unknown> | null => {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  return payload as Record<string, unknown>;
};

const payloadToOpenApiText = (payload: Record<string, unknown> | null | undefined) => {
  if (!payload) return "";
  if (typeof payload.openapi_json === "string" && payload.openapi_json.trim()) {
    return payload.openapi_json;
  }
  if (payload.openapi_document && typeof payload.openapi_document === "object") {
    return JSON.stringify(payload.openapi_document, null, 2);
  }
  if (payload.paths) return JSON.stringify(payload, null, 2);
  return "";
};

const selectedOpenapiArtifact = computed(
  () => openapiArtifacts.value.find((row) => row.id === selectedOpenapiArtifactId.value) ?? null,
);

const latestOpenApiText = computed(() => {
  if (swaggerMode.value === "manual" && openapiDraft.value.trim()) {
    return openapiDraft.value.trim();
  }
  if (swaggerMode.value === "history") {
    return payloadToOpenApiText(extractOpenApiPayload(selectedOpenapiArtifact.value?.payload));
  }
  return payloadToOpenApiText(latestOpenApiPayload.value)
    || payloadToOpenApiText(extractOpenApiPayload(openapiArtifacts.value[0]?.payload));
});

const openapiMeta = computed(() => {
  if (swaggerMode.value === "history") {
    const payload = extractOpenApiPayload(selectedOpenapiArtifact.value?.payload);
    if (!payload) return null;
    return {
      source: String(payload.source || "history"),
      pathCount: Number(payload.path_count || 0),
      remark: typeof payload.remark === "string" ? payload.remark : "",
    };
  }
  const payload =
    latestOpenApiPayload.value || extractOpenApiPayload(openapiArtifacts.value[0]?.payload);
  if (!payload) return null;
  return {
    source: String(payload.source || "—"),
    pathCount: Number(payload.path_count || 0),
    remark: typeof payload.remark === "string" ? payload.remark : "",
  };
});

const swaggerActionLabel = computed(() => {
  if (swaggerMode.value === "url") return "拉取 OpenAPI";
  if (swaggerMode.value === "manual") return "保存为 Swagger 产物";
  if (swaggerMode.value === "history") return "使用选中文档";
  return "生成 Swagger 文档";
});

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

const syncBaseUrlFromProject = (project: Project | null) => {
  if (!project) return;
  baseUrl.value = resolveProjectBaseUrl(project);
};

const ensureProject = () => {
  if (!projectId.value) {
    Message.warning("请先选择项目");
    return false;
  }
  return true;
};

const ensureBaseUrl = () => {
  if (!baseUrl.value.trim()) {
    Message.warning("请先填写被测系统 Base URL（勿使用平台自身地址）");
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
    syncBaseUrlFromProject(selectedProject.value);
  });

const loadFunctionalCases = async () => {
  if (!projectId.value) {
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
    selectedCaseId.value = null;
  }
};

const loadArtifacts = async () => {
  if (!canAiRead.value || !projectId.value) {
    artifacts.value = [];
    return;
  }
  artifacts.value = await aiApi.listAiArtifacts(projectId.value, "api_automation");
};

const loadOpenapiArtifacts = async () => {
  if (!canAiRead.value || !projectId.value) {
    openapiArtifacts.value = [];
    latestOpenApiPayload.value = null;
    selectedOpenapiArtifactId.value = null;
    return;
  }
  openapiArtifacts.value = await aiApi.listAiArtifacts(projectId.value, "openapi_spec");
  const latest = openapiArtifacts.value[0];
  if (latest) {
    if (!selectedOpenapiArtifactId.value
      || !openapiArtifacts.value.some((row) => row.id === selectedOpenapiArtifactId.value)) {
      selectedOpenapiArtifactId.value = latest.id;
    }
    const payload = extractOpenApiPayload(latest.payload);
    if (payload) latestOpenApiPayload.value = payload;
  }
};

const applyOpenApiResult = async (result: {
  payload: Record<string, unknown> | unknown[];
  model: string;
  persisted_ids?: number[];
}) => {
  const payload = extractOpenApiPayload(result.payload);
  if (payload) {
    latestOpenApiPayload.value = payload;
    if (typeof payload.openapi_json === "string") {
      openapiDraft.value = payload.openapi_json;
    }
  }
  await loadOpenapiArtifacts();
  if (result.persisted_ids?.length) {
    selectedOpenapiArtifactId.value = result.persisted_ids[0];
  }
  const pathCount =
    latestOpenApiPayload.value && typeof latestOpenApiPayload.value.path_count === "number"
      ? latestOpenApiPayload.value.path_count
      : 0;
  Message.success(
    `${aiSuccessMessage(result, "Swagger 文档已就绪")}${
      result.persisted_ids?.length ? ` · 产物 #${result.persisted_ids.join(",")}` : ""
    }${pathCount ? ` · ${pathCount} 个路径` : ""}`,
  );
};

const onSwaggerModeChange = (mode: "discover" | "url" | "manual" | "history") => {
  swaggerMode.value = mode;
  if (mode === "url" && !openapiUrl.value.trim()) {
    const root = (selectedProject.value?.code_root || "").trim();
    if (selectedProject.value?.repo_source === "deployed" && /^https?:\/\//i.test(root)) {
      openapiUrl.value = `${root.replace(/\/+$/, "")}/openapi.json`;
    } else if (/^https?:\/\//i.test(baseUrl.value)) {
      openapiUrl.value = `${baseUrl.value.replace(/\/+$/, "")}/openapi.json`;
    }
  }
  if (mode === "history" && !selectedOpenapiArtifactId.value && openapiArtifacts.value.length) {
    selectedOpenapiArtifactId.value = openapiArtifacts.value[0].id;
  }
  if (mode === "manual" && !openapiDraft.value.trim() && latestOpenApiPayload.value) {
    openapiDraft.value = payloadToOpenApiText(latestOpenApiPayload.value);
  }
};

const generateOpenApi = (forceAi = false) => {
  if (!ensureProject()) return;
  if (!canAiExecute.value) {
    Message.warning("缺少 ai.execute 权限");
    return;
  }

  if (swaggerMode.value === "history") {
    if (!openapiArtifacts.value.length) {
      Message.warning("暂无历史产物，可先切换到「读取本地仓库」或「手动录入」");
      return;
    }
    if (!selectedOpenapiArtifact.value) {
      Message.warning("请先选择一条历史 Swagger 产物");
      return;
    }
    const payload = extractOpenApiPayload(selectedOpenapiArtifact.value.payload);
    if (!payload) {
      Message.warning("选中产物没有可用的 OpenAPI 内容");
      return;
    }
    latestOpenApiPayload.value = payload;
    Message.success(`已切换到历史产物 #${selectedOpenapiArtifact.value.id}`);
    return;
  }

  if (swaggerMode.value === "url" && !openapiUrl.value.trim()) {
    Message.warning("请填写 OpenAPI / Swagger URL");
    return;
  }
  if (swaggerMode.value === "manual" && openapiDraft.value.trim().length < 20) {
    Message.warning("请粘贴包含 paths 的 OpenAPI JSON 或 YAML");
    return;
  }

  generatingOpenapi.value = true;
  void store
    .wrap(async () => {
      const result = await aiApi.aiOpenApiSpec(projectId.value!, {
        notes: apiNotes.value.trim(),
        force_ai: swaggerMode.value === "discover" ? forceAi : false,
        mode:
          swaggerMode.value === "url"
            ? "url"
            : swaggerMode.value === "manual"
              ? "manual"
              : "discover",
        openapi_url: openapiUrl.value.trim(),
        openapi_content: openapiDraft.value.trim(),
      });
      await applyOpenApiResult(result);
    })
    .finally(() => {
      generatingOpenapi.value = false;
    });
};

const buildProjectApiInfo = (project: Project) => {
  const lines = [
    `项目名称: ${project.name}`,
    `项目来源: ${sourceLabel(project.repo_source)}`,
    `${locationLabel.value}: ${project.code_root}`,
  ];
  if (project.repo_branch) lines.push(`默认分支: ${project.repo_branch}`);
  if (project.description) lines.push(`项目描述: ${project.description}`);
  if (project.repo_source === "deployed") {
    lines.push(`建议 Base URL: ${project.code_root}`);
  }
  const notes = apiNotes.value.trim();
  if (notes) lines.push(`补充接口说明:\n${notes}`);
  if (latestOpenApiText.value) {
    lines.push(`OpenAPI / Swagger 文档:\n${latestOpenApiText.value.slice(0, 12000)}`);
  }
  return lines.join("\n");
};

const useOpenApiAsNotes = () => {
  if (!latestOpenApiText.value) {
    if (swaggerMode.value === "manual") {
      Message.warning("请先在上方粘贴 OpenAPI JSON / YAML");
      return;
    }
    if (swaggerMode.value === "history") {
      Message.warning("暂无历史产物，可先切换到「读取本地仓库」或「手动录入」");
      return;
    }
    Message.warning("请先生成或拉取 Swagger 文档");
    return;
  }
  apiNotes.value = latestOpenApiText.value;
  Message.success("已将 OpenAPI 填入补充说明，可继续生成接口测试");
};

const copyOpenApi = async () => {
  if (!latestOpenApiText.value) {
    if (swaggerMode.value === "manual") {
      Message.warning("请先在上方粘贴 OpenAPI JSON / YAML");
      return;
    }
    Message.warning("暂无 Swagger 内容可复制");
    return;
  }
  try {
    await navigator.clipboard.writeText(latestOpenApiText.value);
    Message.success("已复制 OpenAPI JSON");
  } catch {
    Message.warning("复制失败，请手动选择文本复制");
  }
};

const downloadOpenApi = () => {
  if (!latestOpenApiText.value) {
    if (swaggerMode.value === "manual") {
      Message.warning("请先在上方粘贴 OpenAPI JSON / YAML");
      return;
    }
    Message.warning("暂无 Swagger 内容可下载");
    return;
  }
  const blob = new Blob([latestOpenApiText.value], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${selectedProject.value?.name || "project"}-openapi.json`;
  anchor.click();
  URL.revokeObjectURL(url);
  Message.success("已开始下载 OpenAPI JSON");
};

const swaggerQuickActions = [
  { key: "copy", label: "复制 JSON", handler: () => void copyOpenApi() },
  { key: "download", label: "下载", handler: downloadOpenApi },
  { key: "fill", label: "填入补充说明", handler: useOpenApiAsNotes },
] as const;

const generateFromProject = () => {
  if (!ensureProject()) return;
  if (!canAiExecute.value) {
    Message.warning("缺少 ai.execute 权限");
    return;
  }
  const project = selectedProject.value;
  if (!project) {
    Message.warning("请先选择项目");
    return;
  }

  generating.value = true;
  void store
    .wrap(async () => {
      const caseInfo = selectedCase.value
        ? formatCaseInfoForApi(selectedCase.value)
        : `基于项目「${project.name}」整体能力，覆盖主流程与异常断言，生成接口自动化场景。`;
      const result = await aiApi.aiApiAutomation(project.id, {
        case_info: caseInfo,
        api_info: buildProjectApiInfo(project),
        case_id: selectedCaseId.value,
      });
      latestPayload.value = result.payload;
      if (!result.persisted_ids?.length) {
        Message.warning("生成完成但未入库，请检查权限或后端日志");
      }
      await loadArtifacts();
      Message.success(
        `${aiSuccessMessage(result, "接口测试已生成")}${
          result.persisted_ids?.length ? ` · 产物 #${result.persisted_ids.join(",")}` : ""
        }`,
      );
      if (result.persisted_ids?.length) {
        Modal.confirm({
          title: "继续下一阶段？",
          content: "接口产物已入库。是否带着当前项目上下文进入性能 Agent？",
          okText: "去性能 Agent",
          cancelText: "留在本页",
          onOk: () => {
            rememberPipelineProjectId(projectId.value);
            return router.push({
              name: "perf-management",
              query: buildPipelineQuery({
                projectId: projectId.value,
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
  selectedArtifactId.value = row.id;
  latestPayload.value = row.payload ?? null;
  viewTitle.value = `接口产物 #${row.id}${row.title ? ` · ${row.title}` : ""}`;
  try {
    viewJsonText.value = JSON.stringify(row.payload ?? {}, null, 2);
  } catch {
    viewJsonText.value = String(row.payload ?? "");
  }
  viewVisible.value = true;
};

const executeArtifact = (row: AiArtifact) => {
  if (!ensureProject()) return;
  if (!ensureBaseUrl()) return;
  if (!canAiExecute.value) {
    Message.warning("缺少 ai.execute 权限");
    return;
  }
  selectedArtifactId.value = row.id;
  executingId.value = row.id;
  void store
    .wrap(async () => {
      const result = await aiApi.executeApiArtifact(projectId.value!, row.id, {
        baseUrl: baseUrl.value,
      });
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
        Message.success(`DSL 执行完成（状态 ${status || "ok"}）`);
      }
    })
    .finally(() => {
      executingId.value = null;
    });
};

const goProjectAi = () => {
  if (!projectId.value) return;
  void router.push({ name: "project-ai", params: { id: String(projectId.value) } });
};

const refreshAll = () => {
  void store.wrap(async () => {
    await loadArtifacts();
    await loadOpenapiArtifacts();
    await loadFunctionalCases();
  });
};

watch(selectedOpenapiArtifactId, (artifactId) => {
  if (swaggerMode.value !== "history" || !artifactId) return;
  const row = openapiArtifacts.value.find((item) => item.id === artifactId);
  const payload = extractOpenApiPayload(row?.payload);
  if (payload) latestOpenApiPayload.value = payload;
});

watch(
  () => [projectId.value, route.name, route.query] as const,
  () => {
    rememberPipelineProjectId(projectId.value);
    syncBaseUrlFromProject(selectedProject.value);
    latestPayload.value = null;
    latestExecResult.value = null;
    void store.runBackground(async () => {
      await loadArtifacts();
      await loadOpenapiArtifacts();
      await loadFunctionalCases();
    });
  },
);

onMounted(() => {
  void loadProjects().then(() => {
    void store.runBackground(async () => {
      await loadArtifacts();
      await loadOpenapiArtifacts();
      await loadFunctionalCases();
    });
  });
});
</script>

<template>
  <div class="artifact-page ai-workspace">
    <div class="ai-stage">
      <AiWorkspaceHero
        title="接口 Agent"
        subtitle="基于当前项目上下文，由 AI 生成并执行接口自动化 DSL"
        badge="AI · API DSL"
        :status-label="busyActive ? 'Agent 工作中' : `产物 ${artifacts.length} 条`"
        :status-tone="busyActive ? 'busy' : 'online'"
      >
        <template #extra>
          <a-space wrap>
            <a-select
              v-model="projectId"
              style="width: 220px"
              placeholder="选择项目"
              allow-search
              :disabled="!projects.length"
            >
              <a-option v-for="item in projects" :key="item.id" :value="item.id">{{ item.name }}</a-option>
            </a-select>
            <a-button type="outline" :loading="store.loading.value" :disabled="!projectId" @click="refreshAll">
              刷新
            </a-button>
          </a-space>
        </template>
      </AiWorkspaceHero>

      <AiPipelineBar current="interface" :handoff="pipelineHandoff" />
      <AiAgentReadyAlert agent-key="interface" />
    </div>

    <AiBusyBanner :active="busyActive" :title="busyTitle" />

    <a-card title="流水指引" class="artifact-card ai-panel ai-guide-rail">
      <div class="ai-guide-rail__row">
        <div class="ai-guide ai-guide--horizontal">
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">01</span>
            <div>
              <div class="ai-guide-step__title">生成依据</div>
              <div class="ai-guide-step__desc">
                以当前项目为主：名称、来源、路径/部署 URL、描述；推荐先生成 Swagger，再生成 DSL。
              </div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">02</span>
            <div>
              <div class="ai-guide-step__title">Swagger → DSL</div>
              <div class="ai-guide-step__desc">
                仓库已有 / 部署可拉取时直接入库；否则扫描路由 + AI 生成 OpenAPI，再输出可执行 YAML DSL。
              </div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">03</span>
            <div>
              <div class="ai-guide-step__title">执行与流转</div>
              <div class="ai-guide-step__desc">
                设置 Base URL 后执行 DSL；也可进入项目 AI 调试，或继续性能 Agent。
              </div>
            </div>
          </div>
        </div>
        <div class="ai-next-hint">
          <p class="ai-next-hint__title">Next · 流水提示</p>
          <p class="ai-next-hint__desc">DSL 入库后，可带着项目上下文进入性能 Agent 生成 k6 压测方案。</p>
        </div>
      </div>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="24">
        <a-card title="按项目生成接口测试" class="artifact-card ai-panel ai-panel--accent">
          <a-typography-text type="secondary">
            选择项目后，AI 会结合项目来源、路径/部署地址与描述生成 DSL；可选绑定功能用例加强场景精度。
          </a-typography-text>

          <div v-if="!selectedProject" class="ai-empty" style="margin-top: 16px">
            <p class="ai-empty__title">请先选择项目</p>
            <p class="ai-empty__desc">在项目管理中创建本地 / 远程 / 已部署项目后，再回到本页生成脚本。</p>
          </div>

          <template v-else>
            <div class="project-context">
              <div class="project-context__head">
                <div class="project-context__name">{{ selectedProject.name }}</div>
                <a-tag :color="sourceTagColor(selectedProject.repo_source)" size="small">
                  {{ sourceLabel(selectedProject.repo_source) }}
                </a-tag>
              </div>
              <div class="project-context__row">
                <span class="project-context__label">{{ locationLabel }}</span>
                <span class="project-context__value" :title="selectedProject.code_root">
                  {{ selectedProject.code_root }}
                </span>
              </div>
              <div v-if="selectedProject.repo_branch" class="project-context__row">
                <span class="project-context__label">默认分支</span>
                <span class="project-context__value">{{ selectedProject.repo_branch }}</span>
              </div>
              <div v-if="selectedProject.description" class="project-context__row">
                <span class="project-context__label">项目描述</span>
                <span class="project-context__value">{{ selectedProject.description }}</span>
              </div>
            </div>

            <div class="artifact-field">
              <div class="artifact-field__label">绑定功能用例（可选）</div>
              <a-select
                v-model="selectedCaseId"
                allow-clear
                allow-search
                placeholder="不绑定则按项目整体能力生成"
                :disabled="!functionalCases.length"
              >
                <a-option v-for="item in functionalCases" :key="item.id" :value="item.id">
                  #{{ item.id }} {{ item.title }}
                </a-option>
              </a-select>
              <a-typography-paragraph type="secondary" style="margin-top: 6px; margin-bottom: 0">
                {{
                  selectedCase
                    ? `将使用用例「${selectedCase.title}」细化场景`
                    : functionalCases.length
                      ? "未绑定时按项目上下文直接生成"
                      : "暂无用例也可直接按项目生成；需要更细场景时可先到需求 Agent"
                }}
              </a-typography-paragraph>
            </div>

            <div class="artifact-field">
              <div class="artifact-field__label">补充接口说明（可选）</div>
              <a-textarea
                v-model="apiNotes"
                :auto-size="{ minRows: 3, maxRows: 8 }"
                placeholder="例如：重点业务模块、鉴权方式；也可先生成 Swagger 再一键填入"
              />
            </div>

            <div class="artifact-field">
              <div class="artifact-field__label">Swagger / OpenAPI</div>
              <div class="swagger-modes">
                <button
                  v-for="mode in swaggerModes"
                  :key="mode.key"
                  type="button"
                  class="swagger-mode"
                  :class="{ 'swagger-mode--active': swaggerMode === mode.key }"
                  @click="onSwaggerModeChange(mode.key)"
                >
                  {{ mode.label }}
                </button>
              </div>
              <a-typography-paragraph type="secondary" style="margin: 8px 0 12px">
                {{ swaggerModes.find((item) => item.key === swaggerMode)?.hint }}
              </a-typography-paragraph>

              <div v-if="swaggerMode === 'url'" class="artifact-field" style="margin-top: 0">
                <a-input
                  v-model="openapiUrl"
                  allow-clear
                  placeholder="例如 https://api.example.com/openapi.json"
                >
                  <template #prefix>URL</template>
                </a-input>
              </div>

              <div v-else-if="swaggerMode === 'manual'" class="artifact-field" style="margin-top: 0">
                <a-textarea
                  v-model="openapiDraft"
                  :auto-size="{ minRows: 8, maxRows: 16 }"
                  placeholder="粘贴 OpenAPI / Swagger 的 JSON 或 YAML（需包含 paths）"
                  class="openapi-preview"
                />
              </div>

              <div v-else-if="swaggerMode === 'history'" class="artifact-field" style="margin-top: 0">
                <a-select
                  v-model="selectedOpenapiArtifactId"
                  allow-search
                  placeholder="选择历史 Swagger 产物"
                  :disabled="!openapiArtifacts.length"
                  style="width: 100%"
                >
                  <a-option v-for="item in openapiArtifacts" :key="item.id" :value="item.id">
                    #{{ item.id }} {{ item.title || "OpenAPI" }} · {{ item.model_name }}
                  </a-option>
                </a-select>
                <div v-if="!openapiArtifacts.length" class="ai-empty" style="margin-top: 12px">
                  <p class="ai-empty__title">暂无历史产物</p>
                  <p class="ai-empty__desc">可先通过其他方式生成一份，再回来选用。</p>
                  <a-space wrap style="margin-top: 8px">
                    <a-button size="small" type="outline" @click="onSwaggerModeChange('discover')">
                      去读取本地仓库
                    </a-button>
                    <a-button size="small" type="outline" @click="onSwaggerModeChange('url')">
                      去拉取 JSON
                    </a-button>
                    <a-button size="small" type="outline" @click="onSwaggerModeChange('manual')">
                      去手动录入
                    </a-button>
                  </a-space>
                </div>
              </div>

              <div class="swagger-toolbar">
                <a-button
                  v-if="canAiExecute"
                  type="outline"
                  status="success"
                  class="swagger-toolbar__primary"
                  :loading="generatingOpenapi || store.loading.value"
                  @click="generateOpenApi(false)"
                >
                  {{ swaggerActionLabel }}
                </a-button>
                <a-button
                  v-if="canAiExecute && swaggerMode === 'discover'"
                  type="outline"
                  class="swagger-toolbar__primary"
                  :loading="generatingOpenapi"
                  @click="generateOpenApi(true)"
                >
                  强制 AI 重写
                </a-button>
                <button
                  v-for="action in swaggerQuickActions"
                  :key="action.key"
                  type="button"
                  class="swagger-action"
                  @click="action.handler()"
                >
                  {{ action.label }}
                </button>
              </div>

              <div v-if="openapiMeta" class="openapi-meta">
                <a-tag size="small" color="arcoblue">来源 {{ openapiMeta.source }}</a-tag>
                <a-tag size="small">路径 {{ openapiMeta.pathCount }}</a-tag>
                <span v-if="openapiMeta.remark" class="openapi-meta__remark">{{ openapiMeta.remark }}</span>
              </div>

              <a-textarea
                v-if="swaggerMode !== 'manual' && latestOpenApiText"
                :model-value="latestOpenApiText"
                readonly
                :auto-size="{ minRows: 8, maxRows: 16 }"
                class="openapi-preview"
              />
              <div
                v-else-if="swaggerMode === 'discover' && !latestOpenApiText"
                class="ai-empty"
                style="margin-top: 12px"
              >
                <p class="ai-empty__title">尚未生成 Swagger</p>
                <p class="ai-empty__desc">选择上方获取方式后，点击对应操作按钮。</p>
              </div>
            </div>
            <div v-if="canAiExecute" class="ai-field" style="margin-top: 12px">
              <div class="ai-field__label">执行参数</div>
                <a-input v-model="baseUrl" placeholder="被测系统 Base URL，例如 https://api.example.com">
                <template #prefix>Base URL</template>
              </a-input>
              <a-typography-paragraph type="secondary" style="margin-top: 6px; margin-bottom: 0">
                已部署项目会自动带入访问地址；仍可手动覆盖。
              </a-typography-paragraph>
            </div>
            <a-space wrap style="margin-top: 12px">
              <a-button
                v-if="canAiExecute"
                type="primary"
                class="ai-action-btn"
                :loading="generating || store.loading.value"
                @click="generateFromProject"
              >
                AI 生成接口测试
              </a-button>
            </a-space>
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
          </template>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="接口测试产物" class="artifact-card ai-panel" style="margin-top: 16px">
      <template #extra>
        <a-tag color="arcoblue">共 {{ artifacts.length }} 条</a-tag>
      </template>

      <a-empty v-if="!canAiRead" description="缺少 ai.read 权限" />
      <div v-else-if="!artifacts.length" class="ai-empty">
        <p class="ai-empty__title">还没有生成产物</p>
        <p class="ai-empty__desc">选择项目后点击「AI 生成接口测试」，结果会入库显示在这里。</p>
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
              执行 DSL
            </a-button>
            <a-button type="text" size="small" @click="goProjectAi">去调试</a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>
  </div>

  <a-modal
    v-model:visible="viewVisible"
    :title="viewTitle"
    :footer="false"
    unmount-on-close
    width="780px"
    :body-style="{ paddingTop: '12px' }"
  >
    <div class="artifact-view-modal">
      <div class="artifact-view-modal__toolbar">
        <a-typography-text type="secondary">产物 JSON（可复制）</a-typography-text>
        <a-typography-text copyable :copy-text="viewJsonText">复制</a-typography-text>
      </div>
      <pre class="ai-payload artifact-view-modal__json">{{ viewJsonText }}</pre>
    </div>
  </a-modal>
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

.project-context {
  margin-top: 16px;
  margin-bottom: 4px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(14, 165, 233, 0.2);
  background: linear-gradient(160deg, rgba(14, 165, 233, 0.08), rgba(255, 255, 255, 0.92));
}

.project-context__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.project-context__name {
  font-size: 16px;
  font-weight: 650;
  color: var(--color-text-1);
}

.project-context__row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 8px;
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.5;
}

.project-context__label {
  color: var(--color-text-3);
}

.project-context__value {
  color: var(--color-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-all;
}

.openapi-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}

.openapi-meta__remark {
  font-size: 12px;
  color: var(--color-text-3);
}

.openapi-preview {
  margin-top: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.swagger-modes {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.swagger-mode {
  width: auto;
  margin-top: 0;
  padding: 8px 10px;
  border: 1px solid var(--color-border-2);
  border-radius: 10px;
  background: var(--color-bg-2);
  color: var(--color-text-2);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.swagger-mode:hover {
  border-color: rgba(14, 165, 233, 0.45);
  color: var(--color-text-1);
}

.swagger-mode--active {
  border-color: rgba(14, 165, 233, 0.55);
  background: linear-gradient(160deg, rgba(14, 165, 233, 0.1), rgba(255, 255, 255, 0.92));
  color: var(--color-text-1);
  font-weight: 600;
}

.swagger-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  align-items: center;
}

.swagger-toolbar__primary {
  border-radius: 10px;
}

.swagger-action {
  width: auto;
  margin-top: 0;
  padding: 6px 12px;
  border: 1px solid var(--color-border-2);
  border-radius: 10px;
  background: var(--color-bg-2);
  color: var(--color-text-1);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease;
}

.swagger-action:hover {
  border-color: rgba(14, 165, 233, 0.45);
  background: rgba(14, 165, 233, 0.1);
  transform: translateY(-1px);
}

.swagger-action:active {
  transform: translateY(0);
}

@media (max-width: 720px) {
  .swagger-modes {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.artifact-view-modal__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.artifact-view-modal__json {
  max-height: min(65vh, 560px);
  overflow: auto;
  margin: 0;
}
</style>
