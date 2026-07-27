<script setup lang="ts">
import { onMounted, ref } from "vue";
import { workbenchApi } from "../../api/ai";
import { useProjectScope } from "../../composables/useProjectScope";
import { usePlatformStore } from "../../state/platform";
import type { WorkbenchMessage, WorkbenchSession } from "../../types";

const store = usePlatformStore();
const { projectId } = useProjectScope();

const modules = [
  { value: "functional_cases", label: "功能用例" },
  { value: "requirement_review", label: "需求评审" },
  { value: "api_automation", label: "接口测试" },
  { value: "perf_plan", label: "性能测试" },
  { value: "security_scan", label: "安全测试" },
];

const sessions = ref<WorkbenchSession[]>([]);
const activeSessionId = ref<number | null>(null);
const messages = ref<WorkbenchMessage[]>([]);
const newModule = ref("functional_cases");
const chatInput = ref("");
const useRag = ref(true);
const applyResult = ref<Record<string, unknown> | null>(null);

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
