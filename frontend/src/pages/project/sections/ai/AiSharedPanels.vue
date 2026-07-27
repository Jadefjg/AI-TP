<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { computed, ref } from "vue";
import { aiApi } from "../../../../api/ai";
import { adminApi } from "../../../../api/admin";
import { useProjectAiContext } from "./useProjectAiContext";

const {
  projectId,
  store,
  aiForm,
  hasAiExecute,
  hasAiRead,
  aiArtifacts,
  securityJobs,
  loadAiArtifacts,
  loadSecurityJobs,
  requestPickArtifact,
  executeArtifact,
} = useProjectAiContext();

const securityReviewNote = ref("");
const feedbackNote = ref("");

const feedbackReady = computed(() => {
  return Boolean(aiForm.feedbackOriginal.trim() && aiForm.feedbackCorrected.trim());
});

const fillOriginalFromArtifact = (item: {
  id?: number | string;
  module_type?: string;
  payload?: unknown;
  title?: string | null;
}) => {
  const payload = item.payload;
  const text =
    typeof payload === "string" ? payload : JSON.stringify(payload ?? item, null, 2);
  aiForm.feedbackOriginal = text.slice(0, 8000);
  if (item.module_type) {
    const known = [
      "functional_cases",
      "requirement_review",
      "api_automation",
      "perf_plan",
      "security_scan",
    ];
    if (known.includes(item.module_type)) {
      aiForm.feedbackModule = item.module_type;
    }
  }
  Message.success("已填入产物内容到「AI 原始输出」，请补充人工修正后提交");
};

const runExecuteArtifact = (artifactId: number, moduleType: string) =>
  store.wrap(() => executeArtifact(artifactId, moduleType));

const reviewSecurityFinding = (jobId: number, findingIndex: number, status: string) =>
  store.wrap(async () => {
    await aiApi.reviewSecurityFinding(projectId.value, jobId, findingIndex, {
      status,
      note: securityReviewNote.value,
      feed_prompt: true,
    });
    await loadSecurityJobs();
    Message.success(status === "false_positive" ? "已标记误报" : "已确认问题");
  });

const submitCaseFeedback = () => {
  const originalText = aiForm.feedbackOriginal.trim();
  const correctedText = aiForm.feedbackCorrected.trim();
  if (!originalText) {
    Message.warning("请填写 AI 原始输出");
    return;
  }
  if (!correctedText) {
    Message.warning("请填写人工修正内容");
    return;
  }
  if (originalText === correctedText) {
    Message.warning("修正内容与原始输出相同，请填写差异点后再提交");
    return;
  }
  void store.wrap(async () => {
    const sourceTypeByModule: Record<string, string> = {
      functional_cases: "functional_case",
      requirement_review: "requirement_review",
      api_automation: "api_automation",
      perf_plan: "perf_plan",
      security_scan: "security_scan",
    };
    const result = await adminApi.submitPromptFeedback({
      module_type: aiForm.feedbackModule,
      source_type: sourceTypeByModule[aiForm.feedbackModule] || "manual_edit",
      project_id: projectId.value,
      original_text: originalText,
      corrected_text: correctedText,
      note: feedbackNote.value.trim() || null,
    });
    store.setOut(result);
    aiForm.feedbackOriginal = "";
    aiForm.feedbackCorrected = "";
    feedbackNote.value = "";
    Message.success("修正反馈已提交，可在「AI Prompt 模板库」预览优化建议");
  });
};
</script>

<template>
  <a-divider v-if="hasAiRead" />
  <div v-if="hasAiRead" class="ai-section-title">AI 产物与引擎执行</div>
  <div v-if="hasAiRead" class="ai-chip-rail">
    <span class="ai-chip ai-chip--live">Artifacts</span>
    <span class="ai-chip">{{ aiArtifacts.length }} 条</span>
    <a-button type="primary" class="ai-action-btn" size="mini" @click="loadAiArtifacts">刷新产物</a-button>
  </div>

  <div v-if="hasAiRead && !aiArtifacts.length" class="ai-empty" style="margin-top: 8px">
    <p class="ai-empty__title">暂无 AI 产物</p>
    <p class="ai-empty__desc">在上方模块生成接口 DSL / 压测 / 安全策略后，产物会出现在这里。</p>
  </div>

  <a-card
    v-for="item in aiArtifacts"
    :key="String(item.id)"
    size="small"
    class="ai-panel"
    style="margin-top: 8px"
  >
    <template #title>{{ item.title || item.module_type }} #{{ item.id }}</template>
    <template #extra>
      <a-space v-if="hasAiExecute">
        <a-button
          v-if="store.hasPermission('prompt.write')"
          size="mini"
          @click="fillOriginalFromArtifact(item)"
        >
          填入反馈
        </a-button>
        <a-button
          v-if="item.module_type === 'api_automation'"
          size="mini"
          @click="runExecuteArtifact(Number(item.id), 'api_automation')"
        >
          DSL
        </a-button>
        <a-button
          v-if="item.module_type === 'api_automation'"
          size="mini"
          @click="requestPickArtifact(Number(item.id))"
        >
          编辑
        </a-button>
        <a-button
          v-if="item.module_type === 'perf_plan'"
          size="mini"
          @click="runExecuteArtifact(Number(item.id), 'perf_plan')"
        >
          k6
        </a-button>
        <a-button
          v-if="item.module_type === 'security_scan'"
          size="mini"
          status="warning"
          @click="runExecuteArtifact(Number(item.id), 'security_scan')"
        >
          扫描
        </a-button>
      </a-space>
    </template>
    <pre class="ai-payload" style="max-height: 200px">{{ JSON.stringify(item.payload, null, 2) }}</pre>
  </a-card>

  <a-card
    v-if="securityJobs.length"
    title="安全扫描记录"
    size="small"
    class="ai-panel"
    style="margin-top: 12px"
  >
    <div class="ai-chip-rail">
      <span class="ai-chip">Security Jobs</span>
      <span class="ai-chip">{{ securityJobs.length }}</span>
    </div>
    <a-input
      v-model="securityReviewNote"
      placeholder="复核备注（误报 / 确认时一并提交）"
      style="margin-bottom: 8px"
    />
    <a-list :data="securityJobs">
      <template #item="{ item }">
        <a-list-item>
          <a-list-item-meta
            :title="`Job #${item.id} · ${item.engine || 'builtin'}`"
            :description="String(item.target_url)"
          />
          <template #actions>
            <a-button size="mini" @click="aiApi.openSecurityReportHtml(projectId, Number(item.id))">
              HTML
            </a-button>
            <a-button size="mini" @click="aiApi.downloadSecurityReportPdf(projectId, Number(item.id))">
              PDF
            </a-button>
          </template>
          <a-tag :color="item.status === 'failed' ? 'red' : 'green'">{{ item.status }}</a-tag>
        </a-list-item>
        <div v-for="(f, idx) in (item.findings || []).slice(0, 5)" :key="idx" style="padding-left: 16px">
          <a-space wrap>
            <span>{{ f.vul_type }} [{{ f.risk_level }}]</span>
            <a-button size="mini" @click="reviewSecurityFinding(Number(item.id), idx, 'confirmed')">
              确认
            </a-button>
            <a-button
              size="mini"
              status="warning"
              @click="reviewSecurityFinding(Number(item.id), idx, 'false_positive')"
            >
              误报
            </a-button>
          </a-space>
        </div>
      </template>
    </a-list>
  </a-card>

  <a-card
    v-if="store.hasPermission('prompt.write')"
    title="Prompt 修正反馈"
    size="small"
    class="ai-panel ai-panel--accent"
    style="margin-top: 12px"
  >
    <div class="ai-chip-rail">
      <span class="ai-chip ai-chip--live">Feedback Loop</span>
      <span class="ai-chip">人工闭环</span>
    </div>
    <a-alert
      type="info"
      show-icon
      style="margin-bottom: 12px"
      message="请同时填写「AI 原始输出」与「人工修正内容」后再提交；也可点产物上的「填入反馈」快速带入原文。"
    />
    <a-form layout="vertical">
      <a-form-item label="目标模块" required>
        <a-select v-model="aiForm.feedbackModule" style="max-width: 280px">
          <a-option value="functional_cases">功能用例 (functional_cases)</a-option>
          <a-option value="requirement_review">需求评审 (requirement_review)</a-option>
          <a-option value="api_automation">接口自动化 (api_automation)</a-option>
          <a-option value="perf_plan">性能压测 (perf_plan)</a-option>
          <a-option value="security_scan">安全扫描 (security_scan)</a-option>
        </a-select>
      </a-form-item>
      <a-form-item label="AI 原始输出" required>
        <a-textarea
          v-model="aiForm.feedbackOriginal"
          :auto-size="{ minRows: 3, maxRows: 10 }"
          placeholder="粘贴 AI 生成的原文，或从上方产物点「填入反馈」"
        />
      </a-form-item>
      <a-form-item label="人工修正内容" required>
        <a-textarea
          v-model="aiForm.feedbackCorrected"
          :auto-size="{ minRows: 3, maxRows: 10 }"
          placeholder="填写你期望的正确表达 / 用例 / 策略内容"
        />
      </a-form-item>
      <a-form-item label="备注（可选）">
        <a-input v-model="feedbackNote" placeholder="例如：漏掉边界场景、术语不准确…" allow-clear />
      </a-form-item>
      <a-button
        type="primary"
        class="ai-action-btn"
        :disabled="!feedbackReady"
        :loading="store.loading.value"
        @click="submitCaseFeedback"
      >
        提交修正反馈
      </a-button>
    </a-form>
  </a-card>
</template>
