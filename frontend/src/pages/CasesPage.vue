<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { aiApi } from "../api/ai";
import { casesApi } from "../api/cases";
import { runsApi } from "../api/runs";
import AiBusyBanner from "../components/ai/AiBusyBanner.vue";
import AiPipelineBar from "../components/ai/AiPipelineBar.vue";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { projectsApi } from "../api/projects";
import {
  PIPELINE_SUITE_NAME,
  buildPipelineQuery,
  parsePipelineQuery,
  recalledPipelineProjectId,
  rememberPipelineProjectId,
} from "../constants/aiPipeline";
import { listTablePagination } from "../constants/listPagination";
import {
  clipRequirementPreview,
  reviewSourceLabel,
  type RequirementReviewRow,
} from "../constants/requirementReview";
import { usePlatformStore } from "../state/platform";
import type { FunctionalCase, Project, TestSuite } from "../types";
import { aiSuccessMessage } from "../utils/aiResult";

const store = usePlatformStore();
const router = useRouter();
const route = useRoute();
const projects = ref<Project[]>([]);
const projectId = ref<number | null>(null);
const reviews = ref<RequirementReviewRow[]>([]);
const selectedReviewId = ref<number | null>(null);
const cases = ref<FunctionalCase[]>([]);
const contexts = ref<Array<Record<string, unknown>>>([]);
const generating = ref(false);
const requirementOverride = ref("");
const selectedCaseId = ref<number | null>(null);
const pipelineSuite = ref<TestSuite | null>(null);
const tablePagination = listTablePagination(10);

const canCaseRead = computed(() => store.hasPermission("case.read"));
const canCaseGenerate = computed(() => store.hasPermission("case.generate"));
const canCaseWrite = computed(() => store.hasPermission("case.write"));
const canAiRead = computed(() => store.hasPermission("ai.read"));
const canRunExecute = computed(() => store.hasPermission("run.execute"));

const selectedReview = computed(
  () => reviews.value.find((row) => row.id === selectedReviewId.value) ?? null,
);

const requirementText = computed(() => {
  const override = requirementOverride.value.trim();
  if (override) return override;
  return (selectedReview.value?.requirement_text || "").trim();
});

const normalizeRequirementKey = (text: string | null | undefined) =>
  (text || "").replace(/\s+/g, " ").trim().slice(0, 20000);

const caseMatchesSelectedReview = (row: FunctionalCase, reviewText: string) => {
  const src = normalizeRequirementKey(row.source_requirement);
  const req = normalizeRequirementKey(reviewText);
  if (!src || !req) return false;
  if (src === req) return true;
  const prefixLen = Math.min(800, src.length, req.length);
  if (prefixLen < 40) return false;
  return src.startsWith(req.slice(0, prefixLen)) || req.startsWith(src.slice(0, prefixLen));
};

/** Cases belonging to the currently selected requirement review (by source_requirement). */
const displayedCases = computed(() => {
  const reviewText = (selectedReview.value?.requirement_text || "").trim();
  if (!reviewText) return cases.value;
  return cases.value.filter((row) => caseMatchesSelectedReview(row, reviewText));
});

const selectReview = (record: RequirementReviewRow) => {
  selectedReviewId.value = record.id;
  requirementOverride.value = (record.requirement_text || "").trim();
  const matched = displayedCases.value;
  if (!matched.some((row) => row.id === selectedCaseId.value)) {
    selectedCaseId.value = matched[0]?.id ?? null;
  }
};

const caseColumns = [
  { title: "ID", dataIndex: "id", width: 72, align: "center" as const },
  { title: "标题", dataIndex: "title", ellipsis: true, tooltip: true, minWidth: 200 },
  { title: "模块", dataIndex: "module", width: 120, ellipsis: true },
  { title: "优先级", dataIndex: "priority", width: 90, align: "center" as const },
  { title: "步骤数", slotName: "steps", width: 88, align: "center" as const },
  { title: "操作", slotName: "actions", width: 220, align: "center" as const, fixed: "right" as const },
];

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

const pipelineHandoff = computed(() => ({
  projectId: projectId.value,
  reviewId: selectedReviewId.value,
  caseId: selectedCaseId.value,
}));

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
      return;
    }
    reviews.value = await aiApi.listRequirementReviews(projectId.value);
    const wanted = parsePipelineQuery(route.query as Record<string, unknown>).reviewId;
    if (wanted && reviews.value.some((row) => row.id === wanted)) {
      selectedReviewId.value = wanted;
    } else if (!reviews.value.some((row) => row.id === selectedReviewId.value)) {
      selectedReviewId.value = reviews.value[0]?.id ?? null;
    }
    const current = reviews.value.find((row) => row.id === selectedReviewId.value);
    requirementOverride.value = (current?.requirement_text || "").trim();
  });

const loadCases = () =>
  store.runBackground(async () => {
    if (!canCaseRead.value || !projectId.value) {
      cases.value = [];
      selectedCaseId.value = null;
      pipelineSuite.value = null;
      return;
    }
    cases.value = await casesApi.listCases(projectId.value);
    const suites = await casesApi.listTestSuites(projectId.value);
    pipelineSuite.value = suites.find((row) => row.name === PIPELINE_SUITE_NAME) ?? null;
    const reviewText = (
      reviews.value.find((row) => row.id === selectedReviewId.value)?.requirement_text || ""
    ).trim();
    const scoped = reviewText
      ? cases.value.filter((row) => caseMatchesSelectedReview(row, reviewText))
      : cases.value;
    const wanted = parsePipelineQuery(route.query as Record<string, unknown>).caseId;
    if (wanted && scoped.some((row) => row.id === wanted)) {
      selectedCaseId.value = wanted;
    } else if (!scoped.some((row) => row.id === selectedCaseId.value)) {
      selectedCaseId.value = scoped[0]?.id ?? null;
    }
  });

const fillFromReview = () => {
  const text = (selectedReview.value?.requirement_text || "").trim();
  if (!text) {
    Message.warning("当前评审记录没有需求正文，请先在需求管理中重新分析");
    return;
  }
  requirementOverride.value = text;
  Message.success("已填入需求正文");
};

const generateWithAgent = () => {
  if (!ensureProject()) return;
  const text = requirementText.value;
  if (text.length < 10) {
    Message.warning("请选择需求评审记录，或粘贴至少 10 个字符的需求正文");
    return;
  }
  generating.value = true;
  void store
    .wrap(async () => {
      const result = await casesApi.genCasesAgent(projectId.value!, text);
      cases.value = result.cases;
      contexts.value = result.contexts;
      Message.success(
        `${aiSuccessMessage({ model: "agent", used_fallback: false }, `AI Agent 已生成 ${result.cases.length} 条用例`)}${
          result.contexts.length ? `（知识库命中 ${result.contexts.length}）` : ""
        }`,
      );
      await loadCases();
      if (result.cases.length) {
        selectedCaseId.value = result.cases[0].id;
        Modal.confirm({
          title: "继续下一阶段？",
          content: "用例已入库并挂入智能流水套件。是否继续接口测试，或先执行功能套件？",
          okText: "去接口测试",
          cancelText: "留在本页",
          onOk: () => goInterface(result.cases[0]?.id),
        });
      }
    })
    .finally(() => {
      generating.value = false;
    });
};

const runPipelineSuite = () => {
  if (!ensureProject()) return;
  if (!canRunExecute.value) {
    Message.warning("缺少 run.execute 权限");
    return;
  }
  if (!pipelineSuite.value) {
    Message.warning("尚未创建智能流水套件，请先生成或转换用例");
    return;
  }
  void store.wrap(async () => {
    const run = await runsApi.startRun(projectId.value!, ["functional"], {
      suite_id: pipelineSuite.value!.id,
    });
    Message.success(`已发起功能套件 Run #${run.id}`);
    await router.push({ name: "task-run-detail", params: { runId: String(run.id) } });
  });
};

const generateBasic = () => {
  if (!ensureProject()) return;
  const text = requirementText.value;
  if (text.length < 10) {
    Message.warning("请选择需求评审记录，或粘贴至少 10 个字符的需求正文");
    return;
  }
  generating.value = true;
  void store
    .wrap(async () => {
      cases.value = await casesApi.genCases(projectId.value!, text);
      contexts.value = [];
      Message.success(`已生成 ${cases.value.length} 条用例`);
    })
    .finally(() => {
      generating.value = false;
    });
};

const convertReviewFindings = () => {
  if (!ensureProject() || !selectedReviewId.value) {
    Message.warning("请先选择一条需求评审记录");
    return;
  }
  void store.wrap(async () => {
    const result = await aiApi.convertReviewToCases(projectId.value!, selectedReviewId.value!);
    await loadCases();
    const suiteHint = result.suite_id ? `，已挂入套件 #${result.suite_id}` : "";
    Message.success(`已将评审问题转换为 ${result.count} 条用例${suiteHint}`);
  });
};

const deleteCase = (row: FunctionalCase) => {
  if (!projectId.value) return;
  Modal.confirm({
    title: "删除用例",
    content: `确认删除用例「${row.title}」？`,
    okText: "删除",
    cancelText: "取消",
    onOk: () =>
      store.wrap(async () => {
        await casesApi.deleteCase(projectId.value!, row.id);
        await loadCases();
        Message.success("已删除");
      }),
  });
};

const goRequirements = () => {
  void router.push({
    name: "requirements",
    query: buildPipelineQuery({ projectId: projectId.value, reviewId: selectedReviewId.value }),
  });
};

const goProjectCases = () => {
  if (!projectId.value) return;
  void router.push({ name: "project-cases", params: { id: String(projectId.value) } });
};

const goInterface = (caseId?: number | null) => {
  const id = caseId ?? selectedCaseId.value ?? displayedCases.value[0]?.id ?? null;
  rememberPipelineProjectId(projectId.value);
  void router.push({
    name: "interface-management",
    query: buildPipelineQuery({
      projectId: projectId.value,
      reviewId: selectedReviewId.value,
      caseId: id,
    }),
  });
};

watch(projectId, (value) => {
  rememberPipelineProjectId(value);
  requirementOverride.value = "";
  contexts.value = [];
  void loadReviews();
  void loadCases();
});

watch(selectedReviewId, (id) => {
  const review = reviews.value.find((row) => row.id === id) ?? null;
  const text = (review?.requirement_text || "").trim();
  // Keep textarea in sync when switching reviews (even if user had edited before).
  if (text && requirementOverride.value !== text) {
    requirementOverride.value = text;
  }
  if (!text) {
    requirementOverride.value = "";
  }
  const matched = cases.value.filter((row) => (text ? caseMatchesSelectedReview(row, text) : true));
  if (!matched.some((row) => row.id === selectedCaseId.value)) {
    selectedCaseId.value = matched[0]?.id ?? null;
  }
});

watch(
  () => cases.value.map((row) => row.id).join(","),
  () => {
    const matched = displayedCases.value;
    if (!matched.some((row) => row.id === selectedCaseId.value)) {
      selectedCaseId.value = matched[0]?.id ?? null;
    }
  },
);

onMounted(() => {
  void loadProjects().then(() => {
    void loadReviews();
    void loadCases();
  });
});
</script>

<template>
  <div class="cases-page ai-workspace">
    <div class="ai-stage">
      <AiWorkspaceHero
        title="测试用例"
        subtitle="挑选需求评审记录，交给 AI Agent 扩写正向 / 异常 / 边界场景；生成后可继续走到接口测试。"
        badge="AI · TEST CASES"
        :status-label="generating ? 'Agent 生成中' : `当前需求 ${displayedCases.length} 条`"
        :status-tone="generating ? 'busy' : 'online'"
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
            <a-button
              type="primary"
              class="ai-action-btn"
              :disabled="!projectId || !pipelineSuite"
              :loading="store.loading.value"
              @click="runPipelineSuite"
            >
              执行流水套件
            </a-button>
            <a-button
              type="outline"
              :loading="store.loading.value"
              :disabled="!projectId"
              @click="
                () => {
                  void loadReviews();
                  void loadCases();
                }
              "
            >
              刷新
            </a-button>
          </a-space>
        </template>
      </AiWorkspaceHero>

      <AiPipelineBar current="cases" :handoff="pipelineHandoff" />
    </div>

    <AiBusyBanner :active="generating" title="AI Agent 正在生成用例" />

    <a-card title="Agent 工作模式" class="cases-card ai-panel ai-guide-rail">
      <div class="ai-guide-rail__row">
        <div class="ai-guide ai-guide--horizontal">
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">01</span>
            <div>
              <div class="ai-guide-step__title">AI Agent 生成</div>
              <div class="ai-guide-step__desc">结合项目知识库检索，覆盖正向、异常、边界等场景并自动入库</div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">02</span>
            <div>
              <div class="ai-guide-step__title">快速生成</div>
              <div class="ai-guide-step__desc">基于需求文本直接生成用例，适合无知识库或快速草稿场景</div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">03</span>
            <div>
              <div class="ai-guide-step__title">评审问题转用例</div>
              <div class="ai-guide-step__desc">将需求歧义 / 逻辑缺失 / 可测性 / 业务风险条目转成验证用例</div>
            </div>
          </div>
        </div>
        <div class="ai-next-hint">
          <p class="ai-next-hint__title">Next · 流水提示</p>
          <p class="ai-next-hint__desc">用例入库后，可带 case_id 进入接口测试，生成并执行 DSL。</p>
        </div>
      </div>
      <a-collapse v-if="contexts.length" style="margin-top: 12px">
        <a-collapse-item header="Agent 知识库检索上下文" key="contexts">
          <a-list :bordered="false" size="small">
            <a-list-item v-for="(ctx, index) in contexts" :key="index">
              <a-list-item-meta
                :title="String(ctx.title || ctx.source || `片段 ${index + 1}`)"
                :description="String(ctx.content_preview || '')"
              />
            </a-list-item>
          </a-list>
        </a-collapse-item>
      </a-collapse>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="24">
        <a-card title="从需求生成用例" class="cases-card ai-panel ai-panel--accent">
          <a-typography-text type="secondary">
            选择评审记录后，用 Agent（含知识库）生成用例；也可快速草稿，或把评审发现问题直接转成验证用例。
          </a-typography-text>

          <div class="cases-field">
            <div class="cases-field__label">需求评审来源</div>
            <div v-if="!reviews.length" class="ai-empty">
              <p class="ai-empty__title">还没有可生成的评审</p>
              <p class="ai-empty__desc">先到需求管理完成一次 AI 分析，再回来这里一键扩写用例。</p>
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
              @row-click="(record: RequirementReviewRow) => selectReview(record)"
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
            <a-space wrap style="margin-top: 8px">
              <a-button size="small" :disabled="!selectedReview" @click="fillFromReview">
                填入选中需求正文
              </a-button>
              <a-button
                v-if="store.hasPermission('ai.execute')"
                size="small"
                :disabled="!selectedReviewId"
                @click="convertReviewFindings"
              >
                评审问题转用例
              </a-button>
            </a-space>
          </div>

          <div class="cases-field">
            <div class="cases-field__label">需求正文（生成输入）</div>
            <a-textarea
              v-model="requirementOverride"
              :auto-size="{ minRows: 6, maxRows: 14 }"
              placeholder="自动使用选中评审的需求正文；也可在此粘贴/编辑后再生成"
            />
            <a-typography-paragraph type="secondary" style="margin-top: 8px; margin-bottom: 0">
              当前有效字数：{{ requirementText.length }}
              <template v-if="selectedReview"> · 已选评审 #{{ selectedReview.id }}</template>
            </a-typography-paragraph>
            <a-space wrap style="margin-top: 12px">
              <a-button
                v-if="canCaseGenerate"
                type="primary"
                class="ai-action-btn"
                :loading="generating || store.loading.value"
                @click="generateWithAgent"
              >
                AI Agent 生成用例
              </a-button>
              <a-button
                v-if="canCaseGenerate"
                :loading="generating || store.loading.value"
                @click="generateBasic"
              >
                快速生成
              </a-button>
              <a-button v-if="displayedCases.length" type="outline" @click="() => goInterface()">
                继续接口测试
              </a-button>
            </a-space>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="用例列表" class="cases-card ai-panel" style="margin-top: 16px">
      <template #extra>
        <a-space>
          <a-tag color="arcoblue">
            共 {{ displayedCases.length }} 条
            <template v-if="selectedReview"> · 评审 #{{ selectedReview.id }}</template>
          </a-tag>
          <a-button size="small" :disabled="!projectId" @click="goProjectCases">项目内编辑</a-button>
        </a-space>
      </template>

      <a-empty v-if="!canCaseRead" description="缺少 case.read 权限" />
      <div v-else-if="!displayedCases.length" class="ai-empty">
        <p class="ai-empty__title">
          {{ selectedReview ? `评审 #${selectedReview.id} 还没有对应用例` : "还没有用例" }}
        </p>
        <p class="ai-empty__desc">
          {{
            selectedReview
              ? "切换上方需求后会同步正文；点「AI Agent 生成用例」或「评审问题转用例」即可生成并显示在这里。"
              : "选中一条需求评审，点「AI Agent 生成用例」，结果会自动出现在这里。"
          }}
        </p>
      </div>
      <a-table
        v-else
        :data="displayedCases"
        :columns="caseColumns"
        row-key="id"
        :loading="store.loading.value"
        :pagination="tablePagination"
        :scroll="{ x: 960 }"
        :row-class="(record: FunctionalCase) => (record.id === selectedCaseId ? 'ai-row--active' : '')"
        @row-click="(record: FunctionalCase) => (selectedCaseId = record.id)"
      >
        <template #steps="{ record }">
          {{ Array.isArray(record.steps) ? record.steps.length : 0 }}
        </template>
        <template #actions="{ record }">
          <a-space :size="4">
            <a-button type="text" size="small" @click.stop="goInterface(record.id)">生成接口</a-button>
            <a-button type="text" size="small" @click.stop="goProjectCases">查看</a-button>
            <a-button
              v-if="canCaseWrite"
              type="text"
              size="small"
              status="danger"
              @click.stop="deleteCase(record)"
            >
              删除
            </a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<style scoped>
.cases-card :deep(.arco-card-body) {
  padding-top: 12px;
}

.cases-field + .cases-field {
  margin-top: 16px;
}

.cases-field__label {
  margin-bottom: 8px;
  color: var(--color-text-1);
  font-weight: 500;
}

.cases-tips {
  display: grid;
  gap: 10px;
}

.cases-tip {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9), #fff);
}

.cases-tip__title {
  font-size: 13px;
  font-weight: 650;
}

.cases-tip__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-3);
}
</style>
