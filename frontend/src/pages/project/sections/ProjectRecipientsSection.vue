<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { projectsApi } from "../../../api/projects";
import { listTablePagination } from "../../../constants/listPagination";
import { useProjectScope } from "../../../composables/useProjectScope";
import { usePlatformStore } from "../../../state/platform";
import type { Recipient } from "../../../types";

const store = usePlatformStore();
const { projectId } = useProjectScope();

const recipients = ref<Recipient[]>([]);
const form = reactive({ email: "", display_name: "" });
const tablePagination = listTablePagination(10);

const hasWrite = computed(() => store.hasPermission("project.write"));

const columns = [
  { title: "ID", dataIndex: "id", width: 70 },
  { title: "邮箱", dataIndex: "email", ellipsis: true },
  { title: "显示名", dataIndex: "display_name", width: 140 },
  { title: "操作", slotName: "actions", width: 100 },
];

const load = () =>
  store.wrap(async () => {
    recipients.value = await projectsApi.listRecipients(projectId.value);
  });

const add = () =>
  store.wrap(async () => {
    const email = form.email.trim();
    if (!email) throw new Error("请填写邮箱");
    await projectsApi.addRecipient(projectId.value, {
      email,
      display_name: form.display_name.trim() || null,
    });
    form.email = "";
    form.display_name = "";
    await load();
  });

const remove = (row: Recipient) =>
  store.wrap(async () => {
    await projectsApi.deleteRecipient(projectId.value, row.id);
    await load();
  });

onMounted(() => void load());
</script>

<template>
  <a-card title="报告邮件收件人" class="ai-panel" style="margin-top: 16px">
    <div class="ai-chip-rail">
      <span class="ai-chip">Recipients</span>
      <span class="ai-chip">{{ recipients.length }}</span>
    </div>
    <a-typography-text type="secondary">
      用于 Run 详情「发送邮件」、失败告警。未配置 SMTP 时默认写入本地发件箱（SMTP_DRY_RUN）；配置 SMTP_HOST 后真实投递。
    </a-typography-text>
    <a-form v-if="hasWrite" layout="inline" style="margin: 12px 0">
        <a-form-item label="邮箱" required>
          <a-input v-model="form.email" placeholder="qa@example.com" style="width: 220px" />
        </a-form-item>
        <a-form-item label="显示名">
          <a-input v-model="form.display_name" placeholder="QA" style="width: 140px" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="add">添加</a-button>
        </a-form-item>
        <a-form-item>
          <a-button :loading="store.loading.value" @click="load">刷新</a-button>
        </a-form-item>
    </a-form>
      <a-table :columns="columns" :data="recipients" row-key="id" :pagination="tablePagination" size="small">
        <template #actions="{ record }">
          <a-popconfirm
            v-if="hasWrite"
            content="确定删除该收件人？"
            @ok="remove(record)"
          >
            <a-button size="mini" status="danger">删除</a-button>
          </a-popconfirm>
        </template>
      </a-table>
      <div v-if="!recipients.length" class="ai-empty" style="margin-top: 12px">
        <p class="ai-empty__title">暂无收件人</p>
        <p class="ai-empty__desc">添加 QA / 业务邮箱后，失败 Run 与报告可自动投递。</p>
      </div>
  </a-card>
</template>
