<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { aiApi } from "../api/ai";
import AiBusyBanner from "../components/ai/AiBusyBanner.vue";
import AiPipelineBar from "../components/ai/AiPipelineBar.vue";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { projectsApi } from "../api/projects";
import {
  buildPipelineQuery,
  parsePipelineQuery,
  recalledPipelineProjectId,
  rememberPipelineProjectId,
} from "../constants/aiPipeline";
import {
  REQUIREMENT_REVIEW_SECTIONS,
  countReviewIssues,
  type RequirementReviewRow,
} from "../constants/requirementReview";
import { listTablePagination } from "../constants/listPagination";
import { usePlatformStore } from "../state/platform";
import type { AiTaskResult, Project } from "../types";
import { aiSuccessMessage } from "../utils/aiResult";
import { resolveUploadFile, stubArcoUploadRequest } from "../utils/manualUpload";

const store = usePlatformStore();
const router = useRouter();
const route = useRoute();
const projects = ref<Project[]>([]);
const projectId = ref<number | null>(null);
const requirementText = ref("");
const documentUrl = ref("");
const uploadFileList = ref<Array<{ uid: string; name?: string; file?: File }>>([]);
const reviews = ref<RequirementReviewRow[]>([]);
const selectedReviewId = ref<number | null>(null);
const viewDrawerVisible = ref(false);
const viewingReview = ref<RequirementReviewRow | null>(null);
const agentContexts = ref<Array<Record<string, unknown>>>([]);
const llmStatus = ref<{ configured: boolean; provider: string; high_precision_model: string } | null>(null);
const analyzing = ref(false);
const tablePagination = listTablePagination(10);

const canRead = computed(() => store.hasPermission("ai.read"));
const canExecute = computed(() => store.hasPermission("ai.execute"));

const selectedReview = computed(
  () => reviews.value.find((row) => row.id === selectedReviewId.value) ?? reviews.value[0] ?? null,
);

const isOfflineAnalyzer = computed(() => selectedReview.value?.model_name === "local-analyzer");

const llmProviderLabel = computed(() => {
  const provider = llmStatus.value?.provider;
  if (provider === "deepseek") return "DeepSeek";
  if (provider === "openai") return "OpenAI";
  if (provider === "local") return "本地模型";
  return "未配置";
});

const reviewColumns = [
  { title: "ID", dataIndex: "id", width: 64, align: "center" as const },
  { title: "来源", slotName: "source", ellipsis: true, tooltip: true, minWidth: 160 },
  { title: "模型", dataIndex: "model_name", width: 200, ellipsis: true, tooltip: true },
  { title: "问题数", slotName: "issues", width: 80, align: "center" as const },
  { title: "时间", slotName: "createdAt", width: 170 },
  { title: "操作", slotName: "actions", width: 280, align: "left" as const },
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

const sourceLabel = (row: RequirementReviewRow) => row.source_filename || "粘贴文本";

type ReviewIssueItem = {
  pos: string;
  level: string;
  desc: string;
  suggest: string;
};

const sectionItems = (
  key: string,
  review: RequirementReviewRow | null = selectedReview.value,
): ReviewIssueItem[] => {
  const payload = review?.result_json;
  const items = payload?.[key];
  if (!Array.isArray(items)) return [];
  return items
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item) => ({
      pos: String(item.pos ?? item.location ?? item.position ?? "—"),
      level: String(item.level ?? item.severity ?? "—"),
      desc: String(item.desc ?? item.description ?? item.issue ?? ""),
      suggest: String(item.suggest ?? item.suggestion ?? item.advice ?? ""),
    }))
    .filter((item) => item.desc || item.suggest || item.pos !== "—");
};

const viewSectionItems = (key: string) => sectionItems(key, viewingReview.value);

const activeSectionKeys = (review: RequirementReviewRow | null) => {
  const withIssues = REQUIREMENT_REVIEW_SECTIONS.filter((section) => sectionItems(section.key, review).length).map(
    (section) => section.key,
  );
  return withIssues.length ? withIssues : REQUIREMENT_REVIEW_SECTIONS.map((section) => section.key);
};

const selectedActiveKeys = computed(() => activeSectionKeys(selectedReview.value));
const viewingActiveKeys = computed(() => activeSectionKeys(viewingReview.value));
const issueLevelColor = (level: string) => {
  if (level.includes("高") || /high/i.test(level)) return "red";
  if (level.includes("中") || /med/i.test(level)) return "orange";
  return "arcoblue";
};

const viewReview = (record: RequirementReviewRow) => {
  selectedReviewId.value = record.id;
  viewingReview.value = record;
  viewDrawerVisible.value = true;
  const text = (record.requirement_text || "").trim();
  if (text) {
    requirementText.value = text;
  }
  void nextTick(() => {
    document.getElementById("requirement-review-result")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  });
};

const loadLlmStatus = () =>
  store.runBackground(async () => {
    if (!canRead.value) {
      llmStatus.value = null;
      return;
    }
    try {
      llmStatus.value = await aiApi.getLlmStatus();
    } catch {
      llmStatus.value = null;
    }
  });

const loadReviews = () =>
  store.runBackground(async () => {
    if (!canRead.value || !projectId.value) {
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
  });

const ensureProject = () => {
  if (!projectId.value) {
    Message.warning("请先选择项目");
    return false;
  }
  return true;
};

const applyAgentResponse = (result: AiTaskResult) => {
  agentContexts.value = result.contexts ?? [];
};

const llmStatusTone = computed<"online" | "offline" | "busy">(() => {
  if (analyzing.value) return "busy";
  return llmStatus.value?.configured ? "online" : "offline";
});

const llmStatusText = computed(() => {
  if (analyzing.value) return "Agent 分析中";
  if (llmStatus.value?.configured) return `${llmProviderLabel.value} · 在线`;
  return "离线规则模式";
});

const pipelineHandoff = computed(() => ({
  projectId: projectId.value,
  reviewId: selectedReviewId.value,
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

const reviewFromText = () => {
  const text = requirementText.value.trim();
  if (!ensureProject() || !text) {
    Message.warning("请填写需求文本");
    return;
  }
  analyzing.value = true;
  void store
    .wrap(async () => {
      const result = await aiApi.aiRequirementReview(projectId.value!, text);
      applyAgentResponse(result);
      await loadReviews();
      selectedReviewId.value = reviews.value[0]?.id ?? null;
      Message.success(aiSuccessMessage(result, "AI Agent 分析完成"));
    })
    .finally(() => {
      analyzing.value = false;
    });
};

const reviewFromUpload = () => {
  const file = resolveUploadFile(uploadFileList.value[0]);
  if (!ensureProject() || !file) {
    Message.warning("请上传 Word 或 PDF 文档");
    return;
  }
  analyzing.value = true;
  void store
    .wrap(async () => {
      const result = await aiApi.aiRequirementReviewUpload(projectId.value!, file);
      applyAgentResponse(result);
      uploadFileList.value = [];
      await loadReviews();
      selectedReviewId.value = reviews.value[0]?.id ?? null;
      Message.success(aiSuccessMessage(result, "AI Agent 文档分析完成"));
    })
    .finally(() => {
      analyzing.value = false;
    });
};

const reviewFromUrl = () => {
  const url = documentUrl.value.trim();
  if (!ensureProject() || !url) {
    Message.warning("请填写文档链接");
    return;
  }
  analyzing.value = true;
  void store
    .wrap(async () => {
      const result = await aiApi.aiRequirementReviewFromUrl(projectId.value!, url);
      applyAgentResponse(result);
      documentUrl.value = "";
      await loadReviews();
      selectedReviewId.value = reviews.value[0]?.id ?? null;
      Message.success(aiSuccessMessage(result, "AI Agent 链接分析完成"));
    })
    .finally(() => {
      analyzing.value = false;
    });
};

const parseUploadToText = () => {
  const file = resolveUploadFile(uploadFileList.value[0]);
  if (!ensureProject() || !file) {
    Message.warning("请先选择文件");
    return;
  }
  void store.wrap(async () => {
    const parsed = await aiApi.parseRequirementDocument(projectId.value!, file);
    requirementText.value = parsed.text;
    Message.success("文档已解析到文本框");
  });
};

const openHtml = (reviewId: number) => {
  if (!projectId.value) return;
  aiApi.openRequirementReviewHtml(projectId.value, reviewId);
};

const downloadPdf = (reviewId: number) => {
  if (!projectId.value) return;
  void store.wrap(async () => {
    await aiApi.downloadRequirementReviewPdf(projectId.value!, reviewId);
  });
};

const convertToCases = (reviewId: number) => {
  if (!projectId.value) return;
  void store.wrap(async () => {
    const result = await aiApi.convertReviewToCases(projectId.value!, reviewId);
    const suiteHint = result.suite_id ? `，已挂入套件 #${result.suite_id}` : "";
    Message.success(`已转换 ${result.count} 条用例${suiteHint}，正在进入测试用例`);
    rememberPipelineProjectId(projectId.value);
    await router.push({
      name: "cases",
      query: buildPipelineQuery({ projectId: projectId.value, reviewId }),
    });
  });
};

watch(projectId, (value) => {
  rememberPipelineProjectId(value);
  void loadReviews();
});

onMounted(() => {
  void loadProjects().then(() => {
    void loadReviews();
    void loadLlmStatus();
  });
});
</script>

<template>
  <div class="requirements-page ai-workspace">
    <div class="ai-stage">
      <AiWorkspaceHero
        title="需求分析"
        subtitle="上传 Word/PDF 或粘贴需求，AI Agent 会结合知识库找出模糊点、逻辑缺口与可测性风险，并引导你进入下一阶段。"
        badge="AI · REQUIREMENT"
        :status-label="llmStatusText"
        :status-tone="llmStatusTone"
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
            <a-button type="outline" :loading="store.loading.value" :disabled="!projectId" @click="loadReviews">
              刷新
            </a-button>
          </a-space>
        </template>
      </AiWorkspaceHero>

      <AiPipelineBar current="requirements" :handoff="pipelineHandoff" />
    </div>

    <AiBusyBanner :active="analyzing" title="AI Agent 正在评审需求" />

    <a-card
      v-if="canExecute"
      title="Agent 感知维度"
      class="requirements-card ai-panel ai-guide-rail"
    >
      <div class="ai-guide-rail__row">
        <div class="ai-guide ai-guide--horizontal">
          <div
            v-for="(section, index) in REQUIREMENT_REVIEW_SECTIONS"
            :key="section.key"
            class="ai-guide-step"
          >
            <span class="ai-guide-step__no">{{ String(index + 1).padStart(2, "0") }}</span>
            <div>
              <div class="ai-guide-step__title">{{ section.title }}</div>
              <div class="ai-guide-step__desc">{{ section.description }}</div>
            </div>
          </div>
        </div>
        <div class="ai-next-hint">
          <p class="ai-next-hint__title">Next · 流水提示</p>
          <p class="ai-next-hint__desc">
            分析完成后，可一键「转用例」进入测试用例；或沿顶部流水线继续接口 / 性能 / 安全测试。
          </p>
        </div>
      </div>
    </a-card>

    <a-row v-if="canExecute" :gutter="16">
      <a-col :span="24">
        <a-card title="投喂需求给 Agent" class="requirements-card ai-panel ai-panel--accent">
          <a-typography-text type="secondary">
            支持 Word（.docx）、PDF、Markdown/TXT，或粘贴需求原文 / 文档链接。分析过程中会自动检索项目知识库。
          </a-typography-text>

          <div class="requirements-field">
            <div class="requirements-field__label">文档上传</div>
            <a-upload
              v-model:file-list="uploadFileList"
              :auto-upload="false"
              :custom-request="stubArcoUploadRequest"
              :show-retry-button="false"
              :limit="1"
              accept=".docx,.pdf,.md,.markdown,.txt"
              drag
            >
              <div class="ai-empty" style="padding: 18px 12px; border: none; background: transparent">
                <p class="ai-empty__title">拖拽文档到这里</p>
                <p class="ai-empty__desc">或点击选择 .docx / .pdf / .md / .txt</p>
              </div>
            </a-upload>
            <a-space wrap style="margin-top: 8px">
              <a-button size="small" type="outline" @click="parseUploadToText">解析到文本框</a-button>
              <a-button
                size="small"
                type="outline"
                :loading="analyzing || store.loading.value"
                @click="reviewFromUpload"
              >
                上传并 AI 分析
              </a-button>
            </a-space>
          </div>

          <div class="requirements-field">
            <div class="requirements-field__label">文档链接</div>
            <a-input
              v-model="documentUrl"
              placeholder="公开网页 / PDF，或飞书 wiki、docx 链接"
              allow-clear
            />
            <a-typography-paragraph type="secondary" style="margin: 6px 0 0">
              飞书私有文档需登录，直链无法抓取；请设为公开可读、配置 FEISHU_APP_ID/SECRET，或改为上传/粘贴原文。
            </a-typography-paragraph>
            <a-button
              type="outline"
              style="margin-top: 8px"
              :loading="analyzing || store.loading.value"
              @click="reviewFromUrl"
            >
              抓取链接并分析
            </a-button>
          </div>

          <div class="requirements-field">
            <div class="requirements-field__label">需求原文</div>
            <a-textarea
              v-model="requirementText"
              :auto-size="{ minRows: 6, maxRows: 12 }"
              placeholder="粘贴 PRD、用户故事或验收标准… Agent 会通读并给出可执行建议"
            />
            <a-button
              type="primary"
              class="ai-action-btn"
              style="margin-top: 8px"
              :loading="analyzing || store.loading.value"
              @click="reviewFromText"
            >
              开始 AI 分析
            </a-button>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-card
      v-if="selectedReview"
      id="requirement-review-result"
      :title="`评审分析结果 · #${selectedReview.id}`"
      class="requirements-card ai-panel"
      style="margin-top: 16px"
    >
      <template #extra>
        <a-space>
          <a-tag color="arcoblue">评审 #{{ selectedReview.id }}</a-tag>
          <a-tag v-if="!isOfflineAnalyzer" color="purple">AI Agent</a-tag>
          <a-tag :color="isOfflineAnalyzer ? 'orange' : 'green'">{{ selectedReview.model_name }}</a-tag>
          <a-button
            v-if="canExecute"
            type="primary"
            size="mini"
            class="ai-action-btn"
            @click="convertToCases(selectedReview.id)"
          >
            转用例并继续
          </a-button>
        </a-space>
      </template>

      <a-alert
        v-if="isOfflineAnalyzer"
        type="warning"
        show-icon
        style="margin-bottom: 12px"
        title="当前为离线规则分析（local-analyzer）"
      >
        后端未检测到可用 LLM。请在项目根目录 <code>.env</code> 配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 后重启后端服务。
      </a-alert>

      <a-alert
        v-else-if="llmStatus?.configured"
        type="success"
        show-icon
        style="margin-bottom: 12px"
        :title="`AI Agent 已连接（${llmProviderLabel}）`"
      >
        当前分析由 {{ selectedReview.model_name }} 模型执行，长文档将自动分段合并结果。
      </a-alert>

      <a-collapse v-if="agentContexts.length" style="margin-bottom: 12px">
        <a-collapse-item header="Agent 知识库检索上下文" key="contexts">
          <a-list :bordered="false" size="small">
            <a-list-item v-for="(ctx, index) in agentContexts" :key="index">
              <a-list-item-meta
                :title="String(ctx.title || ctx.source || `片段 ${index + 1}`)"
                :description="String(ctx.content_preview || '')"
              />
            </a-list-item>
          </a-list>
        </a-collapse-item>
      </a-collapse>

      <a-row :gutter="12">
        <a-col v-for="section in REQUIREMENT_REVIEW_SECTIONS" :key="section.key" :span="12" :md="6">
          <a-statistic :title="section.title" :value="sectionItems(section.key).length" />
        </a-col>
      </a-row>

      <a-collapse
        :key="`result-${selectedReview.id}`"
        :default-active-key="selectedActiveKeys"
        style="margin-top: 16px"
      >
        <a-collapse-item
          v-for="section in REQUIREMENT_REVIEW_SECTIONS"
          :key="section.key"
          :header="`${section.title}（${sectionItems(section.key).length}）`"
        >
          <a-empty v-if="!sectionItems(section.key).length" description="未发现问题，这一项看起来很健康" />
          <div v-else class="review-issue-list">
            <div
              v-for="(item, index) in sectionItems(section.key)"
              :key="`${section.key}-${index}`"
              class="review-issue-item"
            >
              <div class="review-issue-item__meta">
                <a-tag size="small" :color="issueLevelColor(item.level)">{{ item.level }}</a-tag>
                <span class="review-issue-item__pos" :title="item.pos">{{ item.pos }}</span>
              </div>
              <div class="review-issue-item__desc">
                <span class="review-issue-item__label">问题</span>
                {{ item.desc || "—" }}
              </div>
              <div class="review-issue-item__suggest">
                <span class="review-issue-item__label">建议</span>
                {{ item.suggest || "—" }}
              </div>
            </div>
          </div>
        </a-collapse-item>
      </a-collapse>
    </a-card>

    <a-card title="评审记录" class="requirements-card ai-panel" style="margin-top: 16px">
      <div v-if="!reviews.length" class="ai-empty">
        <p class="ai-empty__title">还没有评审记录</p>
        <p class="ai-empty__desc">先上传一份需求文档，或粘贴一段 PRD，让 Agent 帮你开第一枪。</p>
      </div>
      <a-table
        v-else
        class="review-records-table"
        :data="reviews"
        :columns="reviewColumns"
        row-key="id"
        :loading="store.loading.value"
        :pagination="tablePagination"
        :scroll="{ x: 980 }"
        :row-class="(record: RequirementReviewRow) => (record.id === selectedReviewId ? 'ai-row--active' : '')"
        @row-click="(record: RequirementReviewRow) => viewReview(record)"
      >
        <template #source="{ record }">
          <span>{{ sourceLabel(record) }}</span>
          <a-tag v-if="record.source_format" size="small" style="margin-left: 6px">{{ record.source_format }}</a-tag>
        </template>
        <template #issues="{ record }">
          {{ countReviewIssues(record.result_json) }}
        </template>
        <template #createdAt="{ record }">
          {{ formatDateTime(record.created_at) }}
        </template>
        <template #actions="{ record }">
          <div class="review-actions" @click.stop>
            <a-button type="text" size="small" @click="viewReview(record)">查看</a-button>
            <a-button type="text" size="small" @click="openHtml(record.id)">HTML</a-button>
            <a-button type="text" size="small" @click="downloadPdf(record.id)">PDF</a-button>
            <a-button
              v-if="canExecute"
              type="text"
              size="small"
              @click="convertToCases(record.id)"
            >
              转用例
            </a-button>
          </div>
        </template>
      </a-table>
    </a-card>

    <a-drawer
      v-model:visible="viewDrawerVisible"
      :width="760"
      unmount-on-close
      class="review-drawer"
      :title="viewingReview ? `评审详情 #${viewingReview.id}` : '评审详情'"
    >
      <template v-if="viewingReview">
        <div class="ai-chip-rail">
          <span class="ai-chip ai-chip--live">Review</span>
          <span class="ai-chip">#{{ viewingReview.id }}</span>
          <span class="ai-chip">{{ viewingReview.model_name }}</span>
        </div>
        <a-descriptions :column="2" bordered size="medium" class="review-drawer__meta" style="margin-bottom: 16px">
          <a-descriptions-item label="来源">{{ sourceLabel(viewingReview) }}</a-descriptions-item>
          <a-descriptions-item label="模型">{{ viewingReview.model_name }}</a-descriptions-item>
          <a-descriptions-item label="时间">{{ formatDateTime(viewingReview.created_at) }}</a-descriptions-item>
          <a-descriptions-item label="问题数">
            {{ countReviewIssues(viewingReview.result_json) }}
          </a-descriptions-item>
        </a-descriptions>

        <a-row :gutter="12" style="margin-bottom: 16px">
          <a-col v-for="section in REQUIREMENT_REVIEW_SECTIONS" :key="section.key" :span="12" :md="6">
            <div class="review-stat">
              <a-statistic :title="section.title" :value="viewSectionItems(section.key).length" />
            </div>
          </a-col>
        </a-row>

        <div class="requirements-field">
          <div class="requirements-field__label">原始需求正文</div>
          <pre class="ai-payload review-source-text">{{
            viewingReview.requirement_text?.trim() || "（该记录未保存需求正文）"
          }}</pre>
        </div>

        <a-collapse
          :key="`drawer-${viewingReview.id}`"
          :default-active-key="viewingActiveKeys"
          style="margin-top: 16px"
        >
          <a-collapse-item
            v-for="section in REQUIREMENT_REVIEW_SECTIONS"
            :key="section.key"
            :header="`${section.title}（${viewSectionItems(section.key).length}）`"
          >
            <a-empty
              v-if="!viewSectionItems(section.key).length"
              description="未发现问题，这一项看起来很健康"
            />
            <div v-else class="review-issue-list">
              <div
                v-for="(item, index) in viewSectionItems(section.key)"
                :key="`${section.key}-${index}`"
                class="review-issue-item"
              >
                <div class="review-issue-item__meta">
                  <a-tag size="small" :color="issueLevelColor(item.level)">{{ item.level }}</a-tag>
                  <span class="review-issue-item__pos" :title="item.pos">{{ item.pos }}</span>
                </div>
                <div class="review-issue-item__desc">
                  <span class="review-issue-item__label">问题</span>
                  {{ item.desc || "—" }}
                </div>
                <div class="review-issue-item__suggest">
                  <span class="review-issue-item__label">建议</span>
                  {{ item.suggest || "—" }}
                </div>
              </div>
            </div>
          </a-collapse-item>
        </a-collapse>

        <a-space style="margin-top: 16px">
          <a-button @click="openHtml(viewingReview.id)">打开 HTML 报告</a-button>
          <a-button @click="downloadPdf(viewingReview.id)">下载 PDF</a-button>
          <a-button
            v-if="canExecute"
            type="primary"
            class="ai-action-btn"
            @click="convertToCases(viewingReview.id)"
          >
            转用例并继续
          </a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<style scoped>
.requirements-card :deep(.arco-card-body) {
  padding-top: 12px;
}

.requirements-field + .requirements-field {
  margin-top: 16px;
}

.requirements-field__label {
  margin-bottom: 8px;
  color: var(--color-text-1);
  font-weight: 500;
}

.requirements-chip-grid {
  display: grid;
  gap: 10px;
}

.requirements-chip {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9), #fff);
}

.requirements-chip__title {
  font-size: 13px;
  font-weight: 650;
  color: var(--color-text-1);
}

.requirements-chip__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-3);
}

.review-source-text {
  max-height: 220px;
  margin-top: 8px;
}

.review-issue-list {
  display: grid;
  gap: 10px;
}

.review-issue-item {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.95), #fff);
}

.review-issue-item__meta {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

.review-issue-item__pos {
  flex: 1;
  min-width: 0;
  color: var(--color-text-3);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.review-issue-item__desc,
.review-issue-item__suggest {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-1);
  word-break: break-word;
}

.review-issue-item__suggest {
  margin-top: 6px;
  color: var(--color-text-2);
}

.review-issue-item__label {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgba(14, 165, 233, 0.1);
  color: #0284c7;
  font-size: 12px;
  font-weight: 500;
}

.review-stat {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(14, 165, 233, 0.18);
  background: linear-gradient(180deg, rgba(240, 249, 255, 0.95), #fff);
}

.review-actions {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.review-actions :deep(.arco-btn) {
  flex: 0 0 auto;
  padding: 0 6px;
  white-space: nowrap;
}

.review-records-table :deep(.arco-table-td) {
  vertical-align: middle;
}

.review-drawer__meta {
  border-radius: 12px;
  overflow: hidden;
}
</style>
