<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { onMounted, reactive, ref } from "vue";
import { adminApi, type SmtpSettings } from "../api/admin";
import { opsApi, type SettingRevision } from "../api/ops";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { listTablePagination } from "../constants/listPagination";
import { usePlatformStore } from "../state/platform";
import type { SystemSetting } from "../types";

const store = usePlatformStore();
const settings = ref<SystemSetting[]>([]);
const revisions = ref<SettingRevision[]>([]);
const settingForm = reactive({ key: "", value: "", description: "" });
const smtp = ref<SmtpSettings | null>(null);
const smtpForm = reactive({
  host: "",
  port: 587,
  user: "",
  password: "",
  use_tls: true,
  use_ssl: false,
  from_addr: "",
  dry_run: true,
});

const resetSettingForm = () => {
  settingForm.key = "";
  settingForm.value = "";
  settingForm.description = "";
};

const columns = [
  { title: "Key", dataIndex: "key", width: 180 },
  { title: "Value", dataIndex: "value", ellipsis: true },
  { title: "描述", dataIndex: "description", ellipsis: true },
  { title: "操作", slotName: "actions", width: 160 },
];

const revisionColumns = [
  { title: "ID", dataIndex: "id", width: 70 },
  { title: "Key", dataIndex: "setting_key", width: 140 },
  { title: "类型", dataIndex: "change_type", width: 100 },
  { title: "旧值", dataIndex: "old_value", ellipsis: true },
  { title: "新值", dataIndex: "new_value", ellipsis: true },
  { title: "时间", dataIndex: "created_at", width: 180 },
  { title: "操作", slotName: "actions", width: 100 },
];

const tablePagination = listTablePagination(10);

const applySmtpToForm = (data: SmtpSettings) => {
  smtp.value = data;
  smtpForm.host = data.host || "";
  smtpForm.port = data.port || 587;
  smtpForm.user = data.user || "";
  smtpForm.password = "";
  smtpForm.use_tls = data.use_tls;
  smtpForm.use_ssl = data.use_ssl;
  smtpForm.from_addr = data.from_addr || "";
  smtpForm.dry_run = data.dry_run;
};

const loadSmtp = async () => {
  if (!store.hasPermission("settings.read")) return;
  const data = await adminApi.getSmtpSettings();
  applySmtpToForm(data);
};

const loadRevisions = async (key?: string) => {
  if (!store.hasPermission("settings.read")) return;
  revisions.value = await opsApi.listSettingRevisions(key);
};

const load = () =>
  store.wrap(async () => {
    settings.value = await adminApi.listSettings();
    await loadSmtp();
    await loadRevisions();
    store.setOut({ settings: settings.value, smtp: smtp.value, revisions: revisions.value });
  });

const upsert = () => {
  if (!settingForm.key.trim()) {
    Message.warning("请填写配置 Key");
    return;
  }
  Modal.confirm({
    title: "确认保存配置？",
    content: `将修改「${settingForm.key.trim()}」，变更会写入修订历史并可回滚。`,
    onOk: () =>
      store.wrap(async () => {
        const result = await adminApi.upsertSetting({
          key: settingForm.key.trim(),
          value: settingForm.value,
          description: settingForm.description || null,
        });
        store.setOut(result);
        resetSettingForm();
        await load();
        Message.success("配置已保存");
      }),
  });
};

const remove = (key: string) =>
  store.wrap(async () => {
    const result = await adminApi.deleteSetting(key);
    store.setOut(result);
    await load();
  });

const fillForm = (row: SystemSetting) => {
  settingForm.key = row.key;
  settingForm.value = row.value;
  settingForm.description = row.description || "";
  void loadRevisions(row.key);
};

const rollback = (rev: SettingRevision) => {
  if (!store.hasPermission("settings.write")) return;
  Modal.confirm({
    title: "确认回滚到该修订？",
    content: `将把「${rev.setting_key}」恢复为旧值（或删除），并再次记入审计。`,
    onOk: () =>
      store.wrap(async () => {
        await opsApi.rollbackSetting(rev.id);
        Message.success("已回滚");
        await load();
      }),
  });
};

const fillQqPreset = () => {
  smtpForm.host = "smtp.qq.com";
  smtpForm.port = 465;
  smtpForm.use_ssl = true;
  smtpForm.use_tls = false;
  if (smtpForm.user.includes("@")) {
    smtpForm.from_addr = smtpForm.user.trim();
  }
  Message.info("已填入 QQ 邮箱 SMTP 预设（端口 465 / SSL）。用户名请填完整 QQ 邮箱，密码填授权码。");
};

const saveSmtp = () =>
  store.wrap(async () => {
    const host = smtpForm.host.trim();
    const user = smtpForm.user.trim();
    const fromAddr = smtpForm.from_addr.trim() || user;
    if (host && /qq\.com/i.test(host) && user && !user.includes("@")) {
      Message.warning("QQ 邮箱用户名须为完整邮箱（如 name@qq.com），不能填 admin");
      return;
    }
    if (host && user.includes("@") && (!fromAddr || fromAddr === "noreply@example.com")) {
      Message.warning("请将发件人 From 设置为与用户名相同的邮箱");
      return;
    }
    let useSsl = smtpForm.use_ssl;
    let useTls = smtpForm.use_tls;
    const port = Number(smtpForm.port) || 587;
    if (port === 465) {
      useSsl = true;
      useTls = false;
    } else if (port === 587) {
      useSsl = false;
      useTls = true;
    }
    const body: Record<string, unknown> = {
      host,
      port,
      user,
      use_tls: useTls,
      use_ssl: useSsl,
      from_addr: fromAddr,
      dry_run: smtpForm.dry_run,
    };
    if (smtpForm.password.trim()) {
      body.password = smtpForm.password.trim();
    }
    const data = await adminApi.updateSmtpSettings(body);
    applySmtpToForm(data);
    store.setOut(data);
    Message.success(
      data.warning
        ? `SMTP 已保存，但仍有配置问题：${data.warning}`
        : data.configured
          ? "SMTP 已保存，发送报告将真实投递"
          : "SMTP 主机为空：发送仍会写入本地发件箱",
    );
  });

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="ai-workspace ai-page-fill">
    <AiWorkspaceHero
      title="平台配置"
      subtitle="系统配置 · 邮件 SMTP、平台开关与运行参数（变更留痕可回滚）"
      badge="AI · SETTINGS"
      status-label="配置域就绪"
      status-tone="online"
    >
      <template #extra>
        <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="load">
          刷新
        </a-button>
      </template>
    </AiWorkspaceHero>

    <a-card title="邮件 SMTP" class="ai-panel" style="margin-bottom: 16px">
      <a-alert
        v-if="smtp"
        :type="smtp.warning ? 'warning' : smtp.configured ? 'success' : 'warning'"
        show-icon
        style="margin-bottom: 12px"
        :title="
          smtp.warning
            ? 'SMTP 配置不完整，发送可能失败'
            : smtp.configured
              ? 'SMTP 已配置，可真实发送'
              : '尚未配置 SMTP'
        "
      >
        {{ smtp.hint }}
      </a-alert>
      <a-form v-if="store.hasPermission('settings.write')" layout="vertical" style="max-width: 640px">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="SMTP 主机">
              <a-input v-model="smtpForm.host" placeholder="如 smtp.qq.com" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="端口">
              <a-input-number v-model="smtpForm.port" :min="1" :max="65535" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="用户名（邮箱）">
              <a-input v-model="smtpForm.user" placeholder="your@qq.com" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="smtp?.password_set ? '密码 / 授权码（已设置，留空则不改）' : '密码 / 授权码'">
              <a-input-password v-model="smtpForm.password" placeholder="QQ 邮箱请填授权码" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="发件人 From">
              <a-input v-model="smtpForm.from_addr" placeholder="通常与用户名相同" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="选项">
              <a-space wrap>
                <a-checkbox v-model="smtpForm.use_ssl">SSL（465）</a-checkbox>
                <a-checkbox v-model="smtpForm.use_tls">STARTTLS（587）</a-checkbox>
                <a-checkbox v-model="smtpForm.dry_run">无主机时写本地发件箱</a-checkbox>
              </a-space>
            </a-form-item>
          </a-col>
        </a-row>
        <a-space>
          <a-button type="primary" class="ai-action-btn" @click="saveSmtp">保存 SMTP</a-button>
          <a-button @click="fillQqPreset">填入 QQ 邮箱预设</a-button>
        </a-space>
      </a-form>
      <a-typography-text v-else type="secondary">需要 settings.write 权限才能修改 SMTP。</a-typography-text>
    </a-card>

    <a-card
      v-if="store.hasPermission('settings.write')"
      title="新增 / 更新"
      class="ai-panel"
      style="margin-bottom: 16px"
    >
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="8"><a-input v-model="settingForm.key" placeholder="Key" /></a-col>
          <a-col :span="8"><a-input v-model="settingForm.value" placeholder="Value" /></a-col>
          <a-col :span="8"><a-input v-model="settingForm.description" placeholder="描述" /></a-col>
        </a-row>
        <a-button type="primary" class="ai-action-btn" style="margin-top: 8px" @click="upsert">保存</a-button>
      </a-form>
    </a-card>

    <a-card title="配置列表" class="ai-panel" style="margin-bottom: 16px">
      <a-table :data="settings" :columns="columns" row-key="id" :pagination="tablePagination">
        <template #actions="{ record }">
          <a-space>
            <a-button size="mini" @click="fillForm(record)">编辑</a-button>
            <a-popconfirm
              v-if="store.hasPermission('settings.write')"
              content="确认删除？"
              @ok="remove(record.key)"
            >
              <a-button size="mini" status="danger">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-card title="配置修订历史（可回滚）" class="ai-panel ai-fill-panel">
      <a-table :data="revisions" :columns="revisionColumns" row-key="id" :pagination="tablePagination">
        <template #actions="{ record }">
          <a-button
            v-if="store.hasPermission('settings.write')"
            size="mini"
            status="warning"
            @click="rollback(record)"
          >
            回滚
          </a-button>
        </template>
      </a-table>
    </a-card>
  </div>
</template>
