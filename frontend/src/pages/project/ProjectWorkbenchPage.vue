<script setup lang="ts">
import { onMounted, ref } from "vue";
import { workbenchApi, agentWorkflowApi } from "../../api/ai";
import { useProjectScope } from "../../composables/useProjectScope";
import { usePlatformStore } from "../../state/platform";
import type { WorkbenchMessage, WorkbenchSession } from "../../types";

const store = usePlatformStore();
const { projectId } = useProjectScope();

const modules = [
  { value: "requirement_review", label: "需求 Agent" },
  { value: "functional_cases", label: "需求 Agent · 用例" },
  { value: "api_automation", label: "接口 Agent" },
  { value: "perf_plan", label: "性能 Agent" },
  { value: "security_scan", label: "安全 Agent" },
];

const sessions = ref<WorkbenchSession[]>([]);
const activeSessionId = ref<number | null>(null);
const messages = ref<WorkbenchMessage[]>([]);
const newModule = ref("functional_cases");
const chatInput = ref("");
const useRag = ref(true);
const applyResult = ref<Record<string, unknown> | null>(null);
const workflow = ref<any>(null);
const requirementText = ref("");
const reviewNote = ref("");
const workflows = ref<any[]>([]);
const startWorkflow = () => store.wrap(async () => {
  if (!requirementText.value.trim()) return;
  workflow.value = await agentWorkflowApi.create(projectId.value, { requirement_text: requirementText.value.trim() });
  workflows.value = [workflow.value, ...workflows.value.filter((item) => item.id !== workflow.value.id)];
});
const loadWorkflows = () => store.wrap(async () => {
  workflows.value = await agentWorkflowApi.list(projectId.value);
  if (!workflow.value && workflows.value.length) workflow.value = workflows.value[0];
});
const selectWorkflow = (item: any) => store.wrap(async () => { workflow.value = await agentWorkflowApi.get(projectId.value, item.id); });
const reviewStep = (step: any, status: string) => store.wrap(async () => { workflow.value = await agentWorkflowApi.review(projectId.value, workflow.value.id, step.id, status, reviewNote.value); reviewNote.value = ""; });
const retryStep = (step: any) => store.wrap(async () => { workflow.value = await agentWorkflowApi.retry(projectId.value, workflow.value.id, step.id); });
const previewStep = (step: any) => store.wrap(async () => { step.handoffPreview = await agentWorkflowApi.preview(projectId.value, workflow.value.id, step.id); });

const roleLabel = (role: string) => {
  if (role === "assistant") return "Agent";
  if (role === "user") return "你";
  return role;
};

const loadSessions = () =>
  store.wrap(async () => {
    sessions.value = await workbenchApi.listWorkbenchSessions(projectId.value);
    if (!activeSessionId.value && sessions.value.length) {
      activeSessionId.value = sessions.value[0].id;
      await loadMessages();
    }
  });

const loadMessages = async () => {
  if (!activeSessionId.value) return;
  messages.value = await workbenchApi.listWorkbenchMessages(projectId.value, activeSessionId.value);
};

const createSession = () =>
  store.wrap(async () => {
    const row = await workbenchApi.createWorkbenchSession(projectId.value, {
      module_type: newModule.value,
      title: `${newModule.value} 会话`,
    });
    sessions.value.unshift(row);
    activeSessionId.value = row.id;
    messages.value = [];
  });

const sendChat = () =>
  store.wrap(async () => {
    if (!activeSessionId.value || !chatInput.value.trim()) return;
    const res = await workbenchApi.workbenchChat(projectId.value, activeSessionId.value, {
      message: chatInput.value.trim(),
      use_rag: useRag.value,
    });
    messages.value.push(res.user, res.assistant);
    chatInput.value = "";
  });

const applySession = () =>
  store.wrap(async () => {
    if (!activeSessionId.value) return;
    applyResult.value = await workbenchApi.applyWorkbenchSession(projectId.value, activeSessionId.value);
  });

onMounted(() => {
  void loadSessions();
  void loadWorkflows();
});
</script>

<template>
  <a-row :gutter="16">
    <a-col :span="6">
      <a-card title="模块会话" size="small" class="ai-panel">
        <div class="ai-chip-rail">
          <span class="ai-chip ai-chip--live">Workbench</span>
          <span class="ai-chip">{{ sessions.length }} 个会话</span>
        </div>
        <a-select v-model="newModule" style="width: 100%; margin-bottom: 8px">
          <a-option v-for="item in modules" :key="item.value" :value="item.value">{{ item.label }}</a-option>
        </a-select>
        <a-button
          block
          type="primary"
          class="ai-action-btn"
          :disabled="!store.hasPermission('workbench.execute')"
          @click="createSession"
        >
          新建会话
        </a-button>
        <div v-if="!sessions.length" class="ai-empty" style="margin-top: 12px">
          <p class="ai-empty__title">暂无会话</p>
          <p class="ai-empty__desc">选择模块后新建，开始与 Agent 对话编排。</p>
        </div>
        <a-list v-else style="margin-top: 12px" size="small" :data="sessions">
          <template #item="{ item }">
            <a-list-item
              :class="{ 'ai-session-active': item.id === activeSessionId }"
              style="cursor: pointer"
              @click="
                activeSessionId = item.id;
                loadMessages();
              "
            >
              <a-list-item-meta :title="item.title" :description="item.module_type" />
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </a-col>
    <a-col :span="18">
      <a-card title="Agent 工作流" size="small" style="margin-bottom: 16px">
        <a-space direction="vertical" fill>
          <a-textarea v-model="requirementText" :auto-size="{ minRows: 2, maxRows: 5 }" placeholder="输入需求后启动 Agent 工作流" />
          <a-space>
            <a-button type="primary" :disabled="!requirementText.trim()" @click="startWorkflow">启动五 Agent 流程</a-button>
            <a-input v-if="workflow" v-model="reviewNote" placeholder="审核备注（可选）" style="width: 220px" />
            <a-select v-if="workflows.length" :model-value="workflow?.id" placeholder="历史工作流" style="width: 220px" @change="(id: number) => selectWorkflow(workflows.find((item) => item.id === id))">
              <a-option v-for="item in workflows" :key="item.id" :value="item.id">#{{ item.id }} · {{ item.status }}</a-option>
            </a-select>
          </a-space>
        </a-space>
        <a-steps v-if="workflow" :current="workflow.current_step" style="margin-top: 16px">
          <a-step v-for="step in workflow.steps" :key="step.id" :title="step.agent_key" :description="`${step.status} · ${step.review_status}`">
            <template #description><span>{{ step.status }} · {{ step.review_status }}</span><a-button size="mini" @click="previewStep(step)">预览交接</a-button><a-button v-if="step.review_status === 'pending_review'" size="mini" type="primary" @click="reviewStep(step, 'approved')">通过</a-button><a-button v-if="step.review_status === 'pending_review'" size="mini" status="danger" @click="reviewStep(step, 'rejected')">驳回</a-button><a-button v-if="step.status === 'failed' || step.status === 'skipped'" size="mini" status="warning" @click="retryStep(step)">重试</a-button><pre v-if="step.handoffPreview" style="max-width: 280px; white-space: pre-wrap">{{ JSON.stringify(step.handoffPreview, null, 2) }}</pre></template>
          </a-step>
        </a-steps>
      </a-card>
      <a-card title="Agent 对话" size="small" class="ai-panel ai-panel--accent">
        <a-space style="margin-bottom: 8px" wrap>
          <a-switch v-model="useRag" checked-text="RAG" unchecked-text="无 RAG" />
          <a-button
            type="primary"
            class="ai-action-btn"
            :disabled="!activeSessionId || !store.hasPermission('workbench.execute')"
            :loading="store.loading.value"
            @click="sendChat"
          >
            发送
          </a-button>
          <a-button :disabled="!activeSessionId" @click="applySession">一键应用</a-button>
        </a-space>
        <a-textarea v-model="chatInput" :rows="3" placeholder="输入需求或追问…" />
        <div v-if="!messages.length" class="ai-empty" style="margin-top: 12px">
          <p class="ai-empty__title">等待指令</p>
          <p class="ai-empty__desc">描述你的测试目标，Agent 会结合 RAG 给出可落地建议。</p>
        </div>
        <div v-else class="ai-chat-feed">
          <div
            v-for="m in messages"
            :key="m.id"
            class="ai-chat-bubble"
            :class="m.role === 'assistant' ? 'ai-chat-bubble--assistant' : 'ai-chat-bubble--user'"
          >
            <div class="ai-chat-bubble__role">{{ roleLabel(m.role) }}</div>
            <pre class="ai-chat-bubble__body">{{ m.content }}</pre>
          </div>
        </div>
        <pre v-if="applyResult" class="ai-payload" style="margin-top: 12px; max-height: 180px">{{
          JSON.stringify(applyResult, null, 2)
        }}</pre>
      </a-card>
    </a-col>
  </a-row>
</template>
