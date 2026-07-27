<script setup lang="ts">
import { onMounted, ref } from "vue";
import { integrationsApi } from "../../api/ai";
import { listTablePagination } from "../../constants/listPagination";
import { useProjectScope } from "../../composables/useProjectScope";
import { usePlatformStore } from "../../state/platform";
import type { CiWebhookConfig } from "../../types";
import { createAsyncSection } from "./createAsyncSection";

const ProjectRecipientsSection = createAsyncSection(() => import("./sections/ProjectRecipientsSection.vue"));

const store = usePlatformStore();
const { projectId } = useProjectScope();

const config = ref<CiWebhookConfig | null>(null);
const deliveries = ref<Array<Record<string, unknown>>>([]);
const tablePagination = listTablePagination(10);
const deliveryColumns = [
  { title: "ID", dataIndex: "id", width: 72 },
  { title: "运行 ID", dataIndex: "run_id", width: 88 },
  { title: "PR", dataIndex: "pr_number", width: 72 },
  { title: "投递键", dataIndex: "delivery_key", ellipsis: true, tooltip: true },
];
const form = ref({
  enabled: true,
  provider: "github",
  default_branch: "main",
  default_kinds: ["unit", "api"],
  pr_comment_enabled: true,
  github_repo: "",
  github_token: "",
  rotate_secret: false,
});

const load = () =>
  store.wrap(async () => {
    config.value = await integrationsApi.getCiConfig(projectId.value);
    form.value = {
      enabled: config.value.enabled,
      provider: config.value.provider,
      default_branch: config.value.default_branch || "main",
      default_kinds: [...(config.value.default_kinds || [])],
      pr_comment_enabled: config.value.pr_comment_enabled,
      github_repo: config.value.github_repo || "",
      github_token: "",
      rotate_secret: false,
    };
    deliveries.value = await integrationsApi.listCiDeliveries(projectId.value);
  });

const save = () =>
  store.wrap(async () => {
    const body: Record<string, unknown> = { ...form.value };
    if (!body.github_token) delete body.github_token;
    config.value = await integrationsApi.updateCiConfig(projectId.value, body);
    await load();
  });

onMounted(() => void load());
</script>

<template>
  <a-card title="CI / Webhook" class="ai-panel" :loading="store.loading.value">
    <div class="ai-chip-rail">
      <span class="ai-chip ai-chip--live">Integrations</span>
      <span class="ai-chip">{{ form.provider || "ci" }}</span>
    </div>
    <a-descriptions v-if="config" bordered :column="1" size="small">
      <a-descriptions-item label="Webhook URL">{{ config.webhook_url_hint }}</a-descriptions-item>
      <a-descriptions-item label="Token（X-CI-Token）">{{ config.secret_masked }}</a-descriptions-item>
    </a-descriptions>
    <a-form layout="vertical" style="margin-top: 16px; max-width: 560px">
      <a-form-item label="启用">
        <a-switch v-model="form.enabled" />
      </a-form-item>
      <a-form-item label="提供商">
        <a-select v-model="form.provider">
          <a-option value="github">GitHub</a-option>
          <a-option value="gitlab">GitLab</a-option>
          <a-option value="generic">Generic</a-option>
        </a-select>
      </a-form-item>
      <a-form-item label="默认分支">
        <a-input v-model="form.default_branch" />
      </a-form-item>
      <a-form-item label="默认 Run 类型">
        <a-select v-model="form.default_kinds" multiple allow-create />
      </a-form-item>
      <a-form-item label="GitHub 仓库 owner/repo">
        <a-input v-model="form.github_repo" placeholder="org/repo" />
      </a-form-item>
      <a-form-item label="GitHub Token（PR 评论，留空不更新）">
        <a-input-password v-model="form.github_token" />
      </a-form-item>
      <a-form-item label="PR 评论回写">
        <a-switch v-model="form.pr_comment_enabled" />
      </a-form-item>
      <a-form-item label="轮换 Secret">
        <a-switch v-model="form.rotate_secret" />
      </a-form-item>
      <a-button
        type="primary"
        class="ai-action-btn"
        :disabled="!store.hasPermission('integration.ci.manage')"
        @click="save"
      >
        保存
      </a-button>
    </a-form>
  </a-card>
  <a-card title="最近投递" class="ai-panel" style="margin-top: 16px">
    <a-table :data="deliveries" :columns="deliveryColumns" :pagination="tablePagination" row-key="id" size="small" />
  </a-card>
  <ProjectRecipientsSection />
</template>
