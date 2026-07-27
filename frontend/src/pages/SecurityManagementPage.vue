<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { aiApi } from "../api/ai";
import { projectsApi } from "../api/projects";
import AiBusyBanner from "../components/ai/AiBusyBanner.vue";
import AiPipelineBar from "../components/ai/AiPipelineBar.vue";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import {
  buildPipelineQuery,
  parsePipelineQuery,
  recalledPipelineProjectId,
  rememberPipelineProjectId,
} from "../constants/aiPipeline";
import { listTablePagination } from "../constants/listPagination";
import { usePlatformStore } from "../state/platform";
import type { AiArtifact, Project } from "../types";
import { aiSuccessMessage } from "../utils/aiResult";

const store = usePlatformStore();
const router = useRouter();
const route = useRoute();

const projects = ref<Project[]>([]);
const projectId = ref<number | null>(null);
const artifacts = ref<AiArtifact[]>([]);
const apiArtifacts = ref<AiArtifact[]>([]);
const selectedApiArtifactId = ref<number | null>(null);
const useApiArtifactContext = ref(true);
const securityJobs = ref<Array<Record<string, unknown>>>([]);
const generating = ref(false);
const executingId = ref<number | null>(null);
const securityNotes = ref("");
const latestPayload = ref<Record<string, unknown> | unknown[] | null>(null);
const viewVisible = ref(false);
const viewTitle = ref("产物详情");
const viewJsonText = ref("");
const latestExecResult = ref<Record<string, unknown> | null>(null);
const targetUrl = ref("http://127.0.0.1:8002/system/health");
const scanMethod = ref("GET");
const paramName = ref("q");
const paramValue = ref("test");
const securityEngine = ref("builtin");
const tablePagination = listTablePagination(10);

const canAiRead = computed(() => store.hasPermission("ai.read"));
const canAiExecute = computed(() => store.hasPermission("ai.execute"));

const selectedProject = computed(
  () => projects.value.find((item) => item.id === projectId.value) ?? null,
);

const selectedApiArtifact = computed(
  () => apiArtifacts.value.find((row) => row.id === selectedApiArtifactId.value) ?? null,
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
  // 跨阶段统一传递「接口 DSL」产物，避免误传安全扫描产物 ID
  artifactId: selectedApiArtifactId.value ?? null,
}));

const busyActive = computed(() => generating.value || executingId.value !== null);
const busyTitle = computed(() => {
  if (generating.value) return "AI 正在根据项目生成安全测试策略";
  if (executingId.value) return "安全扫描执行中";
  return "AI 工作中";
});

const apiDocExtra = computed(() => {
  if (!useApiArtifactContext.value || !selectedApiArtifact.value) return "";
  const payload = selectedApiArtifact.value.payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
  const script = (payload as Record<string, unknown>).script_content;
  return typeof script === "string" ? script : JSON.stringify(payload, null, 2);
});

const artifactColumns = computed(() => [
  { title: "ID", dataIndex: "id", width: 72, align: "center" as const },
  { title: "标题", dataIndex: "title", ellipsis: true, tooltip: true, minWidth: 180 },
  { title: "模型", dataIndex: "model_name", width: 140, ellipsis: true },
  { title: "时间", slotName: "createdAt", width: 168 },
  {
    title: "操作",
    slotName: "actions",
    width: canAiExecute.value ? 240 : 100,
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

const statusLabel = (status: string) => {
  const map: Record<string, string> = {
    passed: "通过",
    completed: "已完成（有发现）",
    skipped: "已跳过",
    failed: "失败",
    running: "执行中",
    pending: "等待中",
  };
  return map[status] || status || "未知";
};

const statusColor = (status: string) => {
  if (status === "failed") return "red";
  if (status === "skipped") return "orange";
  if (status === "completed") return "orangered";
  return "green";
};

const jobReason = (item: Record<string, unknown>) => {
  const detail = item.detail;
  if (!detail || typeof detail !== "object") return "";
  const reason = (detail as { reason?: unknown }).reason;
  return typeof reason === "string" && reason.trim() ? reason : "";
};

const syncTargetFromProject = (project: Project | null) => {
  if (!project) return;
  const root = (project.code_root || "").trim().replace(/\/+$/, "");
  if (project.repo_source === "deployed" && /^https?:\/\//i.test(root)) {
    targetUrl.value = `${root}/system/health`;
  }
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
    syncTargetFromProject(selectedProject.value);
  });

const loadArtifacts = async () => {
  if (!canAiRead.value || !projectId.value) {
    artifacts.value = [];
    return;
  }
  artifacts.value = await aiApi.listAiArtifacts(projectId.value, "security_scan");
};

const loadApiArtifacts = async () => {
  if (!canAiRead.value || !projectId.value) {
    apiArtifacts.value = [];
    selectedApiArtifactId.value = null;
    return;
  }
  apiArtifacts.value = await aiApi.listAiArtifacts(projectId.value, "api_automation");
  const wanted = parsePipelineQuery(route.query as Record<string, unknown>).artifactId;
  if (wanted && apiArtifacts.value.some((row) => row.id === wanted)) {
    selectedApiArtifactId.value = wanted;
    useApiArtifactContext.value = true;
  } else if (!apiArtifacts.value.some((row) => row.id === selectedApiArtifactId.value)) {
    selectedApiArtifactId.value = apiArtifacts.value[0]?.id ?? null;
  }
};

const loadJobs = async () => {
  if (!canAiRead.value || !projectId.value) {
    securityJobs.value = [];
    return;
  }
  securityJobs.value = await aiApi.listSecurityScanJobs(projectId.value);
};

const buildProjectSecurityInput = (project: Project) => {
  const lines = [
    `项目名称: ${project.name}`,
    `项目来源: ${sourceLabel(project.repo_source)}`,
    `${locationLabel.value}: ${project.code_root}`,
  ];
  if (project.repo_branch) lines.push(`默认分支: ${project.repo_branch}`);
  if (project.description) lines.push(`项目描述: ${project.description}`);
  if (project.repo_source === "deployed") {
    lines.push(`建议扫描目标: ${project.code_root}`);
  } else {
    lines.push(`建议扫描目标: ${targetUrl.value}`);
  }
  const notes = securityNotes.value.trim();
  if (notes) lines.push(`补充安全测试说明:\n${notes}`);
  if (apiDocExtra.value) {
    lines.push(`--- 接口 DSL ---\n${apiDocExtra.value.slice(0, 12000)}`);
  }
  lines.push(
    "请输出漏洞类型、风险等级、测试 Payload 与扫描策略，覆盖 SQL 注入、XSS、越权、敏感信息泄露等常见风险。",
  );
  return lines.join("\n");
};

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
      const result = await aiApi.aiSecurityScan(project.id, buildProjectSecurityInput(project));
      latestPayload.value = result.payload;
      if (!result.persisted_ids?.length) {
        Message.warning("生成完成但未入库，请检查权限或后端日志");
      }
      await loadArtifacts();
      Message.success(
        `${aiSuccessMessage(result, "安全测试策略已生成")}${
          result.persisted_ids?.length ? ` · 产物 #${result.persisted_ids.join(",")}` : ""
        }`,
      );
      if (result.persisted_ids?.length) {
        Modal.confirm({
          title: "流水已走完？",
          content: "安全策略已入库。可本页发起扫描，或前往任务中心查看历史 Run。",
          okText: "去任务中心",
          cancelText: "继续扫描",
          onOk: () => router.push({ name: "tasks" }),
        });
      }
    })
    .finally(() => {
      generating.value = false;
    });
};

const viewArtifact = (row: AiArtifact) => {
  latestPayload.value = row.payload ?? null;
  viewTitle.value = `安全策略 #${row.id}${row.title ? ` · ${row.title}` : ""}`;
  try {
    viewJsonText.value = JSON.stringify(row.payload ?? {}, null, 2);
  } catch {
    viewJsonText.value = String(row.payload ?? "");
  }
  viewVisible.value = true;
};

const executeArtifact = (row: AiArtifact) => {
  if (!ensureProject()) return;
  if (!canAiExecute.value) {
    Message.warning("缺少 ai.execute 权限");
    return;
  }
  if (!targetUrl.value.trim()) {
    Message.warning("请填写扫描目标 URL");
    return;
  }
  executingId.value = row.id;
  void store
    .wrap(async () => {
      const result = await aiApi.dispatchSecurityArtifact(projectId.value!, row.id, {
        target_url: targetUrl.value.trim(),
        method: scanMethod.value,
        query_params: { [paramName.value || "q"]: paramValue.value || "test" },
        engine: securityEngine.value,
      });
      latestExecResult.value = result;
      latestPayload.value = row.payload;
      const status = String(result.status || "");
      const findingCount = Array.isArray(result.findings) ? result.findings.length : 0;
      const reason =
        typeof result.reason === "string"
          ? result.reason
          : typeof result.detail === "object" && result.detail && "reason" in (result.detail as object)
            ? String((result.detail as { reason?: unknown }).reason || "")
            : typeof result.detail === "string"
              ? result.detail
              : "";
      if (status === "skipped") {
        Message.warning(`扫描已跳过：${reason || "目标不可达或策略不可用"}`);
      } else if (status === "completed" || findingCount > 0) {
        Message.success(`扫描完成，发现 ${findingCount} 条可疑项，可在下方查看报告`);
      } else if (status === "failed") {
        Message.error(`扫描失败：${reason || "请检查目标地址与策略产物"}`);
      } else {
        Message.success(`安全扫描完成（状态 ${status || "passed"}），可在下方查看报告`);
      }
      await loadJobs();
    })
    .finally(() => {
      executingId.value = null;
    });
};

const openReportHtml = (jobId: number) => {
  if (!projectId.value) return;
  aiApi.openSecurityReportHtml(projectId.value, jobId);
};

const downloadReportPdf = (jobId: number) => {
  if (!projectId.value) return;
  void aiApi.downloadSecurityReportPdf(projectId.value, jobId);
};

const goProjectAi = () => {
  if (!projectId.value) return;
  void router.push({ name: "project-ai", params: { id: String(projectId.value) } });
};

const refreshAll = () => {
  void store.wrap(async () => {
    await loadArtifacts();
    await loadApiArtifacts();
    await loadJobs();
  });
};

watch(
  () => [projectId.value, route.name, route.query] as const,
  () => {
    rememberPipelineProjectId(projectId.value);
    syncTargetFromProject(selectedProject.value);
    latestPayload.value = null;
    latestExecResult.value = null;
    void store.runBackground(async () => {
      await loadArtifacts();
      await loadApiArtifacts();
      await loadJobs();
    });
  },
);

onMounted(() => {
  void loadProjects().then(() => {
    void store.runBackground(async () => {
      await loadArtifacts();
      await loadApiArtifacts();
      await loadJobs();
    });
  });
});
</script>

<template>
  <div class="artifact-page ai-workspace">
    <div class="ai-stage">
      <AiWorkspaceHero
        title="安全测试"
        subtitle="基于当前项目：生成安全测试策略 → 执行扫描 → 查看 HTML/PDF 报告"
        badge="AI · SECURITY"
        :status-label="busyActive ? 'Agent 工作中' : `策略 ${artifacts.length} · 扫描 ${securityJobs.length}`"
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

      <AiPipelineBar current="security" :handoff="pipelineHandoff" />
    </div>

    <AiBusyBanner :active="busyActive" :title="busyTitle" />

    <a-card title="流水指引" class="artifact-card ai-panel ai-guide-rail">
      <div class="ai-guide-rail__row">
        <div class="ai-guide ai-guide--horizontal">
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">01</span>
            <div>
              <div class="ai-guide-step__title">生成策略</div>
              <div class="ai-guide-step__desc">
                以当前项目为主：名称、来源、路径/部署 URL、描述；推荐引用接口 DSL。
              </div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">02</span>
            <div>
              <div class="ai-guide-step__title">发起扫描</div>
              <div class="ai-guide-step__desc">
                填写目标 URL 后对策略产物发起扫描；nuclei/ZAP 未安装时会 skipped 并保留原因。
              </div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">03</span>
            <div>
              <div class="ai-guide-step__title">查看报告</div>
              <div class="ai-guide-step__desc">
                扫描完成后可下载 HTML / PDF 报告，并回到任务中心查看历史 Run。
              </div>
            </div>
          </div>
        </div>
        <div class="ai-next-hint">
          <p class="ai-next-hint__title">Next · 流水提示</p>
          <p class="ai-next-hint__desc">安全策略与扫描完成后，可前往任务中心回顾整条智能流水。</p>
        </div>
      </div>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="24">
        <a-card title="按项目生成安全测试策略" class="artifact-card ai-panel ai-panel--accent">
          <a-typography-text type="secondary">
            选择项目后生成安全 Payload / 策略并入库；设置目标 URL 后发起扫描，再在下方查看测试报告。
          </a-typography-text>

          <div v-if="!selectedProject" class="ai-empty" style="margin-top: 16px">
            <p class="ai-empty__title">请先选择项目</p>
            <p class="ai-empty__desc">在项目管理中创建本地 / 远程 / 已部署项目后，再回到本页生成安全用例。</p>
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

            <div class="sec-steps">
              <div class="sec-step">
                <span class="sec-step__no">1</span>
                <span>生成安全测试策略</span>
              </div>
              <div class="sec-step">
                <span class="sec-step__no">2</span>
                <span>执行扫描</span>
              </div>
              <div class="sec-step">
                <span class="sec-step__no">3</span>
                <span>查看测试报告</span>
              </div>
            </div>

            <div class="artifact-field">
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
                    #{{ item.id }} {{ item.title || "接口测试" }}
                  </a-option>
                </a-select>
              </a-space>
              <a-typography-paragraph type="secondary" style="margin-top: 6px; margin-bottom: 0">
                {{
                  apiArtifacts.length
                    ? "会把真实接口路径/入参注入安全策略生成，提升命中率"
                    : "暂无接口产物，可先到接口测试生成 DSL，或仅按项目描述生成"
                }}
              </a-typography-paragraph>
            </div>

            <div class="artifact-field">
              <div class="artifact-field__label">补充安全说明（可选）</div>
              <a-textarea
                v-model="securityNotes"
                :auto-size="{ minRows: 3, maxRows: 8 }"
                placeholder="例如：登录态字段、敏感接口清单、鉴权方式、重点关注 OWASP 类型…"
              />
            </div>

            <div v-if="canAiExecute" class="ai-field" style="margin-top: 12px">
              <div class="ai-field__label">扫描参数</div>
              <a-space direction="vertical" fill style="width: 100%">
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
                <a-typography-paragraph type="secondary" style="margin-bottom: 0">
                  已部署项目会自动带入访问地址；生成策略后在产物列表点「发起扫描」。
                </a-typography-paragraph>
              </a-space>
            </div>
            <a-button
              v-if="canAiExecute"
              type="primary"
              class="ai-action-btn"
              style="margin-top: 12px"
              :loading="generating || store.loading.value"
              @click="generateFromProject"
            >
              ① AI 生成安全测试策略
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
          </template>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="安全测试策略产物" class="artifact-card ai-panel" style="margin-top: 16px">
      <template #extra>
        <a-tag color="arcoblue">共 {{ artifacts.length }} 条</a-tag>
      </template>

      <a-empty v-if="!canAiRead" description="缺少 ai.read 权限" />
      <div v-else-if="!artifacts.length" class="ai-empty">
        <p class="ai-empty__title">还没有安全策略</p>
        <p class="ai-empty__desc">选择项目后点击「AI 生成安全测试策略」，结果会入库显示在这里。</p>
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
              发起扫描
            </a-button>
            <a-button type="text" size="small" @click="goProjectAi">去调试</a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-card v-if="canAiRead" title="扫描记录与测试报告" class="artifact-card ai-panel" style="margin-top: 16px">
      <template #extra>
        <a-tag>共 {{ securityJobs.length }} 条</a-tag>
      </template>
      <div v-if="!securityJobs.length" class="ai-empty">
        <p class="ai-empty__title">尚无扫描记录</p>
        <p class="ai-empty__desc">生成安全策略后，设置目标 URL，再点「发起扫描」；完成后可查看 HTML/PDF 报告。</p>
      </div>
      <a-list v-else :data="securityJobs" :bordered="false">
        <template #item="{ item }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>
                Job #{{ item.id }} · {{ item.engine || "builtin" }} ·
                {{ statusLabel(String(item.status || "")) }}
              </template>
              <template #description>
                <div>{{ String(item.target_url || "") }}</div>
                <div v-if="jobReason(item)" class="sec-job-reason">{{ jobReason(item) }}</div>
                <div v-if="Array.isArray(item.findings) && item.findings.length" class="sec-job-findings">
                  发现 {{ item.findings.length }} 条可疑项
                </div>
              </template>
            </a-list-item-meta>
            <template #actions>
              <a-button size="mini" type="outline" @click="openReportHtml(Number(item.id))">
                HTML 报告
              </a-button>
              <a-button size="mini" type="outline" @click="downloadReportPdf(Number(item.id))">
                PDF 报告
              </a-button>
            </template>
            <a-tag :color="statusColor(String(item.status || ''))">
              {{ statusLabel(String(item.status || "")) }}
            </a-tag>
          </a-list-item>
        </template>
      </a-list>
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

.sec-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 14px 0 4px;
}

.sec-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  color: var(--color-text-1);
}

.sec-step__no {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

@media (max-width: 720px) {
  .sec-steps {
    grid-template-columns: 1fr;
  }
}
.sec-job-reason {
  margin-top: 4px;
  font-size: 12px;
  color: #c2410c;
  line-height: 1.45;
}

.sec-job-findings {
  margin-top: 4px;
  font-size: 12px;
  color: #0369a1;
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
