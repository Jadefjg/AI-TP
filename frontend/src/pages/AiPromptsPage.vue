<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { adminApi } from "../api/admin";
import { dashboardApi } from "../api/dashboard";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { LIST_PAGE_SIZE_OPTIONS } from "../constants/listPagination";
import { usePlatformStore } from "../state/platform";
import type { AiUsageSummary, PromptTemplate } from "../types";

const store = usePlatformStore();
const MIN_PROMPT_CONTENT_LEN = 10;
const canWrite = computed(() => store.hasPermission("prompt.write"));
const modules = ref<string[]>([]);
const templates = ref<PromptTemplate[]>([]);
const listPagination = reactive({
  current: 1,
  pageSize: 10,
});
const usage = ref<AiUsageSummary | null>(null);
const selectedId = ref<number | null>(null);
const editContent = ref("");
const saveNewVersionBusy = ref(false);
const optimizeModule = ref("functional_cases");
const suggestions = ref<{ feedback_count: number; proposed_append: string } | null>(null);

const createForm = reactive({
  module_type: "requirement_review",
  name: "",
  content: "",
  model_profile: "high_precision",
});

const feedbackForm = reactive({
  module_type: "functional_cases",
  original_text: "",
  corrected_text: "",
  note: "",
});

const paginatedTemplates = computed(() => {
  const start = (listPagination.current - 1) * listPagination.pageSize;
  return templates.value.slice(start, start + listPagination.pageSize);
});

watch(
  () => templates.value.length,
  (total) => {
    const maxPage = Math.max(1, Math.ceil(total / listPagination.pageSize) || 1);
    if (listPagination.current > maxPage) {
      listPagination.current = maxPage;
    }
  },
);

const load = () =>
  store.wrap(async () => {
    modules.value = await adminApi.listAiModules();
    templates.value = await adminApi.listPromptTemplates();
    usage.value = await dashboardApi.getAiUsageSummary();
    store.setOut({ modules: modules.value, usage: usage.value });
  });

const selectTemplate = (row: PromptTemplate) => {
  selectedId.value = row.id;
  editContent.value = row.content;
};

const deleteTemplate = (row: PromptTemplate) => {
  Modal.confirm({
    title: "删除模板",
    content: `确定删除「${row.name}」v${row.version}？删除后不可恢复。`,
    okText: "删除",
    cancelText: "取消",
    okButtonProps: { status: "danger" },
    onOk: () =>
      store.wrap(async () => {
        await adminApi.deletePromptTemplate(row.id);
        if (selectedId.value === row.id) {
          selectedId.value = null;
          editContent.value = "";
        }
        await load();
        Message.success(`模板「${row.name}」v${row.version} 已删除`);
      }),
  });
};

const saveNewVersion = () =>
  (() => {
    // Prevent duplicate submissions when users double-click the button.
    // (Arco's loading disables visually, but there can be a short window before it flips.)
    if (saveNewVersionBusy.value) return;
    if (!selectedId.value) return;
    saveNewVersionBusy.value = true;

    void store.wrap(async () => {
      try {
        const result = await adminApi.updatePromptTemplate(selectedId.value!, {
          content: editContent.value,
          new_version: true,
        });
        store.setOut(result);
        await load();
        selectTemplate(result);
      } finally {
        saveNewVersionBusy.value = false;
      }
    });
  })();

const createTemplate = () => {
  const name = createForm.name.trim();
  const content = createForm.content.trim();
  if (!name) {
    Message.warning("请填写模板名称");
    return;
  }
  if (content.length < MIN_PROMPT_CONTENT_LEN) {
    Message.warning(`模板内容至少 ${MIN_PROMPT_CONTENT_LEN} 个字符`);
    return;
  }
  void store.wrap(async () => {
    const result = await adminApi.createPromptTemplate({
      module_type: createForm.module_type,
      name,
      content,
      model_profile: createForm.model_profile.trim() || "bulk_local",
    });
    store.setOut(result);
    createForm.name = "";
    createForm.content = "";
    await load();
    Message.success("模板已创建");
  });
};

const seedTemplates = () =>
  store.wrap(async () => {
    store.setOut(await adminApi.seedPromptTemplates());
    await load();
    Message.success("内置 Prompt 已导入");
  });

const loadSuggestions = () =>
  void store.wrap(async () => {
    suggestions.value = await adminApi.getPromptSuggestions(optimizeModule.value);
    store.setOut(suggestions.value);
    if (!suggestions.value.feedback_count) {
      Message.warning("当前模块暂无未应用的修正样本，请先提交修正样本");
    }
  });

const applySuggestions = () =>
  void store.wrap(async () => {
    if (!suggestions.value || suggestions.value.feedback_count === 0) {
      suggestions.value = await adminApi.getPromptSuggestions(optimizeModule.value);
    }
    if (!suggestions.value.feedback_count) {
      Message.warning("暂无可用修正样本，请先填写并提交「AI 原始输出」与「人工修正」");
      return;
    }
    if (!suggestions.value.proposed_append?.trim()) {
      Message.warning("优化建议为空，请先提交有效的修正样本");
      return;
    }
    const result = await adminApi.applyPromptSuggestions(optimizeModule.value);
    store.setOut(result);
    await load();
    selectTemplate(result);
    suggestions.value = null;
    Message.success(`已应用到新 Prompt 版本 v${result.version}`);
  });

const submitFeedback = () => {
  const originalText = feedbackForm.original_text.trim();
  const correctedText = feedbackForm.corrected_text.trim();
  if (!originalText) {
    Message.warning("请填写 AI 原始输出");
    return;
  }
  if (!correctedText) {
    Message.warning("请填写人工修正内容");
    return;
  }
  void store.wrap(async () => {
    store.setOut(
      await adminApi.submitPromptFeedback({
        module_type: feedbackForm.module_type,
        source_type: "manual_edit",
        original_text: originalText,
        corrected_text: correctedText,
        note: feedbackForm.note.trim() || null,
      }),
    );
    feedbackForm.original_text = "";
    feedbackForm.corrected_text = "";
    feedbackForm.note = "";
    optimizeModule.value = feedbackForm.module_type;
    suggestions.value = null;
    Message.success("修正样本已提交，可预览优化建议后应用到新版本");
  });
};

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="ai-workspace">
    <AiWorkspaceHero
      title="AI Prompt 模板库"
      subtitle="系统配置 · 版本管理、Token 统计与人工修正闭环"
      badge="AI · PROMPTS"
      status-label="模板库在线"
      status-tone="online"
    >
      <template #extra>
        <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="load">
          刷新
        </a-button>
      </template>
    </AiWorkspaceHero>

    <a-row v-if="usage" :gutter="16">
      <a-col :span="6"
        ><a-card class="ai-panel"><a-statistic title="总调用" :value="usage.total_calls" /></a-card
      ></a-col>
      <a-col :span="6"
        ><a-card class="ai-panel"><a-statistic title="成功" :value="usage.success_calls" /></a-card
      ></a-col>
      <a-col :span="6"
        ><a-card class="ai-panel"
          ><a-statistic title="Prompt Tokens" :value="usage.total_prompt_tokens" /></a-card
      ></a-col>
      <a-col :span="6"
        ><a-card class="ai-panel"
          ><a-statistic title="Completion Tokens" :value="usage.total_completion_tokens" /></a-card
      ></a-col>
    </a-row>

    <a-card title="操作" class="ai-panel" style="margin-top: 16px">
      <a-space>
        <a-button @click="seedTemplates">导入内置 5 套 Prompt</a-button>
      </a-space>
    </a-card>

    <a-row :gutter="16" style="margin-top: 16px">
      <a-col :span="10">
        <a-card title="模板列表" class="ai-panel">
          <a-list :bordered="false">
            <a-list-item
              v-for="row in paginatedTemplates"
              :key="row.id"
              class="template-item"
              :class="{ active: selectedId === row.id }"
              @click="selectTemplate(row)"
            >
              <a-list-item-meta :title="row.name" :description="`${row.module_type} · v${row.version}`" />
              <template #actions>
                <a-space :size="4" @click.stop>
                  <a-tag :color="row.is_active ? 'green' : 'gray'">{{ row.is_active ? "启用" : "停用" }}</a-tag>
                  <a-button
                    v-if="canWrite"
                    type="text"
                    size="mini"
                    status="danger"
                    @click.stop="deleteTemplate(row)"
                  >
                    删除
                  </a-button>
                </a-space>
              </template>
            </a-list-item>
          </a-list>
          <a-pagination
            v-if="templates.length"
            v-model:current="listPagination.current"
            v-model:page-size="listPagination.pageSize"
            class="list-pagination"
            :total="templates.length"
            :show-total="true"
            :show-page-size="true"
            :show-jumper="true"
            :page-size-options="LIST_PAGE_SIZE_OPTIONS"
            :page-size-props="{ style: { width: '116px' } }"
          />
        </a-card>
      </a-col>
      <a-col :span="14">
        <a-card title="编辑模板（保存为新版本）" class="ai-panel">
          <a-textarea v-model="editContent" :auto-size="{ minRows: 14, maxRows: 24 }" />
          <a-button
            type="primary"
            style="margin-top: 8px"
            :disabled="!selectedId || saveNewVersionBusy"
            :loading="store.loading.value || saveNewVersionBusy"
            @click="saveNewVersion"
          >
            保存新版本
          </a-button>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="Prompt 微调闭环" class="ai-panel" style="margin-top: 16px">
      <a-typography-text type="secondary" style="display: block; margin-bottom: 12px">
        流程：提交修正样本 → 预览优化建议 → 应用到新 Prompt 版本
      </a-typography-text>
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form layout="vertical">
            <a-form-item label="模块">
              <a-select v-model="feedbackForm.module_type">
                <a-option v-for="m in modules" :key="m" :value="m">{{ m }}</a-option>
              </a-select>
            </a-form-item>
            <a-form-item label="AI 原始输出" required>
              <a-textarea
                v-model="feedbackForm.original_text"
                placeholder="粘贴 AI 生成的原始文本"
                :auto-size="{ minRows: 4 }"
              />
            </a-form-item>
            <a-form-item label="人工修正" required>
              <a-textarea
                v-model="feedbackForm.corrected_text"
                placeholder="填写期望的正确输出"
                :auto-size="{ minRows: 4 }"
              />
            </a-form-item>
            <a-form-item label="备注">
              <a-input v-model="feedbackForm.note" placeholder="可选" allow-clear />
            </a-form-item>
            <a-button type="primary" :loading="store.loading.value" @click="submitFeedback">提交修正样本</a-button>
          </a-form>
        </a-col>
        <a-col :span="12">
          <a-form layout="vertical">
            <a-form-item label="优化目标模块">
              <a-select v-model="optimizeModule">
                <a-option v-for="m in modules" :key="m" :value="m">{{ m }}</a-option>
              </a-select>
            </a-form-item>
            <a-space>
              <a-button :loading="store.loading.value" @click="loadSuggestions">预览优化建议</a-button>
              <a-button
                type="primary"
                status="success"
                :loading="store.loading.value"
                @click="applySuggestions"
              >
                应用到新 Prompt 版本
              </a-button>
            </a-space>
            <a-alert
              v-if="suggestions"
              style="margin-top: 12px"
              type="info"
              :title="`待应用样本 ${suggestions.feedback_count} 条`"
              :description="suggestions.proposed_append.slice(0, 400) + (suggestions.proposed_append.length > 400 ? '...' : '')"
            />
          </a-form>
        </a-col>
      </a-row>
    </a-card>

    <a-card title="新建模板" class="ai-panel" style="margin-top: 16px">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="模块" required>
              <a-select v-model="createForm.module_type">
                <a-option v-for="m in modules" :key="m" :value="m">{{ m }}</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="名称" required>
              <a-input v-model="createForm.name" placeholder="模板名称" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="模型配置">
              <a-input v-model="createForm.model_profile" placeholder="high_precision / bulk_local" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="模板内容" required>
          <a-textarea
            v-model="createForm.content"
            placeholder="Prompt 正文（至少 10 个字符）"
            :auto-size="{ minRows: 6 }"
          />
        </a-form-item>
        <a-button type="primary" :loading="store.loading.value" @click="createTemplate">创建</a-button>
      </a-form>
    </a-card>
  </div>
</template>

<style scoped>
.template-item {
  cursor: pointer;
}
.template-item.active {
  background: var(--color-fill-2);
}
</style>
