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
const perfJobs = ref<Array<Record<string, unknown>>>([]);
const generating = ref(false);
const executingId = ref<number | null>(null);
const bizNotes = ref("");
const latestPayload = ref<Record<string, unknown> | unknown[] | null>(null);
const latestExecResult = ref<Record<string, unknown> | null>(null);
const viewVisible = ref(false);
const viewTitle = ref("产物详情");
const viewJsonText = ref("");
const baseUrl = ref("http://127.0.0.1:8002");
const perfDistributed = ref(false);
const tableLoading = ref(false);
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
  // 跨阶段统一传递「接口 DSL」产物，供安全/接口页复用上下文
  artifactId: selectedApiArtifactId.value ?? null,
}));

const busyActive = computed(() => generating.value || executingId.value !== null);
const busyTitle = computed(() => {
  if (generating.value) return "AI 正在根据项目生成压测方案";
  if (executingId.value) return "k6 压测下发中（页面下发会自动缩短时长，避免超时）";
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
  const root = (project.code_root || "").trim();
  if (project.repo_source === "deployed" && /^https?:\/\//i.test(root)) {
    baseUrl.value = root.replace(/\/+$/, "");
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
    syncBaseUrlFromProject(selectedProject.value);
  });

const loadArtifacts = async () => {
  if (!canAiRead.value || !projectId.value) {
    artifacts.value = [];
    return;
  }
  artifacts.value = await aiApi.listAiArtifacts(projectId.value, "perf_plan");
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
    perfJobs.value = [];
    return;
  }
  perfJobs.value = await aiApi.listPerfK6Jobs(projectId.value);
};

const buildProjectBizDesc = (project: Project) => {
  const lines = [
    `项目名称: ${project.name}`,
    `项目来源: ${sourceLabel(project.repo_source)}`,
    `${locationLabel.value}: ${project.code_root}`,
  ];
  if (project.repo_branch) lines.push(`默认分支: ${project.repo_branch}`);
  if (project.description) lines.push(`项目描述: ${project.description}`);
  if (project.repo_source === "deployed") {
    lines.push(`建议压测 Base URL: ${project.code_root}`);
  } else {
    lines.push(`建议压测 Base URL: ${baseUrl.value}`);
  }
  const notes = bizNotes.value.trim();
  if (notes) lines.push(`补充业务/压测说明:\n${notes}`);
  lines.push("请基于当前项目设计可执行的 k6 压测方案，覆盖主流程与关键链路。");
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
      const result = await aiApi.aiPerfPlan(project.id, {
        biz_desc: buildProjectBizDesc(project),
        api_doc: apiDocExtra.value || undefined,
      });
      latestPayload.value = result.payload;
      if (!result.persisted_ids?.length) {
        Message.warning("生成完成但未入库，请检查权限或后端日志");
      }
      await loadArtifacts();
      Message.success(
        `${aiSuccessMessage(result, "压测方案已生成")}${
          result.persisted_ids?.length ? ` · 产物 #${result.persisted_ids.join(",")}` : ""
        }`,
      );
      if (result.persisted_ids?.length) {
        Modal.confirm({
          title: "继续下一阶段？",
          content: "压测方案已入库。是否带着当前项目与接口上下文进入安全测试？",
          okText: "去安全测试",
          cancelText: "留在本页",
          onOk: () => {
            rememberPipelineProjectId(projectId.value);
            return router.push({
              name: "security-management",
              query: buildPipelineQuery({
                projectId: projectId.value,
                artifactId: selectedApiArtifactId.value,
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
  latestPayload.value = row.payload ?? null;
  viewTitle.value = `压测方案 #${row.id}${row.title ? ` · ${row.title}` : ""}`;
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
  executingId.value = row.id;
  void store
    .wrap(async () => {
      const result = await aiApi.dispatchPerfArtifact(
        projectId.value!,
        row.id,
        baseUrl.value,
        perfDistributed.value,
      );
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
        Message.success(`k6 下发完成（状态 ${status || "ok"}）`);
      }
      await loadJobs();
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
  tableLoading.value = true;
  void store
    .wrap(async () => {
      await loadArtifacts();
      await loadApiArtifacts();
      await loadJobs();
    })
    .finally(() => {
      tableLoading.value = false;
    });
};

watch(
  () => [projectId.value, route.name, route.query] as const,
  () => {
    rememberPipelineProjectId(projectId.value);
    syncBaseUrlFromProject(selectedProject.value);
    latestPayload.value = null;
    latestExecResult.value = null;
    tableLoading.value = true;
    void store
      .runBackground(async () => {
        await loadArtifacts();
        await loadApiArtifacts();
        await loadJobs();
      })
      .finally(() => {
        tableLoading.value = false;
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
        title="性能测试"
        subtitle="基于当前项目上下文，由 AI 生成并下发 k6 压测方案"
        badge="AI · PERF"
        :status-label="busyActive ? 'Agent 工作中' : `方案 ${artifacts.length} 条`"
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

      <AiPipelineBar current="perf" :handoff="pipelineHandoff" />
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
                以当前项目为主：名称、来源、路径/部署 URL、描述；推荐引用接口 DSL，可选补充压测目标。
              </div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">02</span>
            <div>
              <div class="ai-guide-step__title">压测方案</div>
              <div class="ai-guide-step__desc">
                输出压测模式、并发阶梯、时长、接口权重与 RT/错误率预警阈值，入库为 perf_plan。
              </div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">03</span>
            <div>
              <div class="ai-guide-step__title">下发与流转</div>
              <div class="ai-guide-step__desc">
                设置 Base URL 后下发 k6；无 Worker 时会 skipped 并保留原因，可继续安全测试。
              </div>
            </div>
          </div>
        </div>
        <div class="ai-next-hint">
          <p class="ai-next-hint__title">Next · 流水提示</p>
          <p class="ai-next-hint__desc">压测方案入库后，可带着项目与接口上下文进入安全测试。</p>
        </div>
      </div>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="24">
        <a-card title="按项目生成压测方案" class="artifact-card ai-panel ai-panel--accent">
          <a-typography-text type="secondary">
            选择项目后，AI 会结合来源、路径/部署地址与接口产物生成 k6 压测方案；生成后可直接下发执行。
          </a-typography-text>

          <div v-if="!selectedProject" class="ai-empty" style="margin-top: 16px">
            <p class="ai-empty__title">请先选择项目</p>
            <p class="ai-empty__desc">在项目管理中创建本地 / 远程 / 已部署项目后，再回到本页生成方案。</p>
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
                    ? "会把 DSL 注入压测上下文，提升接口权重与场景精度"
                    : "暂无接口产物，可先到接口测试生成 DSL，或仅按项目描述生成"
                }}
              </a-typography-paragraph>
            </div>

            <div class="artifact-field">
              <div class="artifact-field__label">补充压测说明（可选）</div>
              <a-textarea
                v-model="bizNotes"
                :auto-size="{ minRows: 3, maxRows: 8 }"
                placeholder="例如：目标 QPS、峰值时段、重点接口、SLA/错误率要求…"
              />
            </div>

            <div v-if="canAiExecute" class="ai-field" style="margin-top: 12px">
              <div class="ai-field__label">执行参数</div>
              <a-space direction="vertical" fill style="width: 100%">
                <a-input v-model="baseUrl" placeholder="Base URL，例如 http://127.0.0.1:8002">
                  <template #prefix>Base URL</template>
                </a-input>
                <a-checkbox v-model="perfDistributed">优先分布式调度（有 Worker 时）</a-checkbox>
                <a-typography-paragraph type="secondary" style="margin-bottom: 0">
                  已部署项目会自动带入访问地址；仍可手动覆盖。
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
              AI 生成压测方案
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

    <a-card title="压测方案产物" class="artifact-card ai-panel" style="margin-top: 16px">
      <template #extra>
        <a-tag color="arcoblue">共 {{ artifacts.length }} 条</a-tag>
      </template>

      <a-empty v-if="!canAiRead" description="缺少 ai.read 权限" />
      <div v-else-if="!artifacts.length" class="ai-empty">
        <p class="ai-empty__title">还没有生成产物</p>
        <p class="ai-empty__desc">选择项目后点击「AI 生成压测方案」，结果会入库显示在这里。</p>
      </div>
      <a-table
        v-else
        :data="artifacts"
        :columns="artifactColumns"
        row-key="id"
        :loading="tableLoading"
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
              下发 k6
            </a-button>
            <a-button type="text" size="small" @click="goProjectAi">去调试</a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-card v-if="canAiRead" title="k6 压测任务" class="artifact-card ai-panel" style="margin-top: 16px">
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
          {{ formatDateTime(String(record.created_at || "")) }}
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
