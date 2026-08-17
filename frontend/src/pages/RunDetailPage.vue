<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { API_BASE_URL } from "../api/config";
import { authStore } from "../api/auth-store";
import { projectsApi } from "../api/projects";
import { runsApi } from "../api/runs";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { useRunPoll } from "../composables/useRunPoll";
import type { ExecutionJob, Recipient, ReportEmailResult, Run } from "../types";
import { usePlatformStore } from "../state/platform";

const route = useRoute();
const router = useRouter();
const store = usePlatformStore();

const runId = computed(() => Number(route.params.runId));
const fromTasksCenter = computed(() => route.name === "task-run-detail");
const run = ref<Run | null>(null);
const reportHtml = ref("");
const emailResult = ref<ReportEmailResult | null>(null);
const autoRefresh = ref(true);
const pageLoading = ref(false);

const sendVisible = ref(false);
const sendLoading = ref(false);
const recipients = ref<Recipient[]>([]);
const selectedEmails = ref<string[]>([]);
const extraEmailsText = ref("");
const saveRecipients = ref(true);
const newEmail = ref("");
const newDisplayName = ref("");
const mailStatus = ref<{
  configured: boolean;
  mode: string;
  hint: string;
  host?: string;
  warning?: string | null;
} | null>(null);
const detailVisible = ref(false);
const detailTitle = ref("执行项详情");
const detailJsonText = ref("");

const openItemDetail = (record: { kind?: string; id?: number; detail?: unknown }) => {
  detailTitle.value = `执行项详情 · ${record.kind || `#${record.id ?? ""}`}`.trim();
  try {
    detailJsonText.value = JSON.stringify(record.detail ?? {}, null, 2);
  } catch {
    detailJsonText.value = String(record.detail ?? "");
  }
  detailVisible.value = true;
};

const hasRunExecute = computed(() => store.hasPermission("run.execute"));
const hasReportRead = computed(() => store.hasPermission("report.read"));
const hasReportSend = computed(() => store.hasPermission("report.send"));
const hasProjectWrite = computed(() => store.hasPermission("project.write"));
const hasSettingsRead = computed(() => store.hasPermission("settings.read"));

const emailAlertType = computed(() => {
  if (!emailResult.value) return "info";
  if (!emailResult.value.ok) return "warning";
  if (emailResult.value.mode === "outbox" || emailResult.value.skipped) return "warning";
  return "success";
});

const emailAlertTitle = computed(() => {
  if (!emailResult.value) return "";
  if (!emailResult.value.ok) return "邮件未发送";
  if (emailResult.value.mode === "outbox" || emailResult.value.skipped) return "未真实投递（已写入本地发件箱）";
  return "邮件已发送";
});

const itemColumns = [
  { title: "类型", dataIndex: "kind", width: 110 },
  { title: "状态", slotName: "status", width: 90 },
  { title: "原因", slotName: "reason", ellipsis: true, tooltip: true, minWidth: 160 },
  { title: "退出码", dataIndex: "exit_code", width: 80 },
  { title: "命令", dataIndex: "command", ellipsis: true },
  { title: "详情", slotName: "detail", width: 200 },
];

const RUN_STATUS_LABELS: Record<string, string> = {
  failed: "失败",
  running: "运行中",
  pending: "等待中",
  completed: "已完成",
  cancelled: "已取消",
  skipped: "已跳过",
  passed: "通过",
  error: "错误",
};

const statusLabel = (status: string) => RUN_STATUS_LABELS[status] || status;

const statusColor = (status: string) => {
  if (status === "completed" || status === "passed") return "green";
  if (status === "failed" || status === "error") return "red";
  if (status === "running") return "arcoblue";
  if (status === "cancelled") return "orange";
  if (status === "skipped") return "orange";
  return "gray";
};

const itemReason = (record: { detail?: Record<string, unknown> | null; status?: string }) => {
  const detail = record.detail;
  if (!detail || typeof detail !== "object") return "";
  for (const key of ["reason", "message", "error"]) {
    const v = detail[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  const ai = detail.ai;
  if (ai && typeof ai === "object" && "detail" in (ai as object)) {
    const nested = (ai as { detail?: { reason?: unknown } }).detail;
    if (nested && typeof nested.reason === "string") return nested.reason;
  }
  const legacy = detail.legacy;
  if (legacy && typeof legacy === "object" && "detail" in (legacy as object)) {
    const nested = (legacy as { detail?: { reason?: unknown } }).detail;
    if (nested && typeof nested.reason === "string") return nested.reason;
  }
  return "";
};

const securityJobId = (record: { detail?: Record<string, unknown> | null; kind?: string }) => {
  const detail = record.detail;
  if (!detail || typeof detail !== "object") return null;
  const id = detail.security_job_id;
  if (typeof id === "number" && id > 0) return id;
  if (typeof id === "string" && Number(id) > 0) return Number(id);
  return null;
};

const allItemsSkipped = computed(() => {
  const items = run.value?.items || [];
  return (
    items.length > 0 &&
    items.every((i) => i.status === "skipped") &&
    !items.some((i) => i.status === "failed" || i.status === "error")
  );
});

const openSecurityReport = (jobId: number) => {
  const pid = run.value?.project_id;
  if (!pid) return;
  void import("../api/ai").then(({ aiApi }) => {
    aiApi.openSecurityReportHtml(pid, jobId);
  });
};

const jobStatus = computed(() => run.value?.execution_job?.status ?? "—");
const isActiveRun = computed(() =>
  Boolean(run.value && ["pending", "running"].includes(run.value.status)),
);

const parseExtraEmails = (raw: string) =>
  raw
    .split(/[,;\s]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

const loadRun = (background = false) => {
  const fn = async () => {
    run.value = await runsApi.getRun(runId.value);
    if (!background) {
      store.setOut({ run: run.value });
    }
  };
  if (background) {
    return store.runBackground(fn);
  }
  return store.wrap(fn);
};

const loadReportPreview = () =>
  store.wrap(async () => {
    if (!hasReportRead.value) return;
    if (!run.value || ["pending", "running"].includes(run.value.status)) return;
    reportHtml.value = await runsApi.fetchReportHtml(runId.value);
  });

const loadRecipients = async (options?: { autoSelect?: boolean }) => {
  if (!run.value?.project_id) {
    recipients.value = [];
    return;
  }
  recipients.value = await projectsApi.listRecipients(run.value.project_id);
  const autoSelect = options?.autoSelect !== false;
  if (autoSelect && !selectedEmails.value.length && recipients.value.length) {
    selectedEmails.value = recipients.value.map((r) => r.email);
  }
};

const refreshAll = async (background = false) => {
  await loadRun(background);
  if (run.value && !["pending", "running"].includes(run.value.status)) {
    if (!background) {
      await loadReportPreview();
    }
  }
};

const { start: startPoll, stop: stopPoll, polling } = useRunPoll(run, {
  onSettled: () => {
    void loadReportPreview();
  },
});

const syncPolling = () => {
  if (autoRefresh.value && isActiveRun.value) {
    startPoll(runId.value);
    return;
  }
  stopPoll();
};

watch(autoRefresh, syncPolling);
watch(isActiveRun, syncPolling);

const manualRefresh = async () => {
  pageLoading.value = true;
  try {
    await refreshAll();
    syncPolling();
  } finally {
    pageLoading.value = false;
  }
};

const cancelRun = () =>
  store.wrap(async () => {
    const job = await runsApi.cancelRun(runId.value);
    if (run.value) run.value.execution_job = job as ExecutionJob;
    await refreshAll();
    syncPolling();
  });

const retryRun = () =>
  store.wrap(async () => {
    const job = await runsApi.retryRun(runId.value);
    if (run.value) run.value.execution_job = job as ExecutionJob;
    await refreshAll();
    syncPolling();
  });

const generateReport = () =>
  store.wrap(async () => {
    await runsApi.createReport(runId.value);
    await loadReportPreview();
    Message.success("报告已生成");
  });

const openSendModal = () => {
  sendVisible.value = true;
  void store.wrap(async () => {
    await loadRecipients();
    try {
      mailStatus.value = await runsApi.mailStatus();
    } catch {
      mailStatus.value = null;
    }
  });
};

const addRecipientQuick = () =>
  store.wrap(async () => {
    if (!run.value?.project_id) return;
    const email = newEmail.value.trim();
    if (!email || !email.includes("@")) {
      Message.warning("请填写有效邮箱");
      return;
    }
    if (!hasProjectWrite.value) {
      Message.warning("缺少 project.write 权限，无法保存收件人；可填写临时邮箱后直接发送");
      if (!selectedEmails.value.includes(email.toLowerCase())) {
        selectedEmails.value = [...selectedEmails.value, email.toLowerCase()];
      }
      extraEmailsText.value = [extraEmailsText.value, email].filter(Boolean).join(", ");
      newEmail.value = "";
      return;
    }
    await projectsApi.addRecipient(run.value.project_id, {
      email,
      display_name: newDisplayName.value.trim() || null,
    });
    newEmail.value = "";
    newDisplayName.value = "";
    await loadRecipients();
    Message.success("收件人已添加");
  });

const removeRecipient = (row: Recipient) =>
  store.wrap(async () => {
    if (!run.value?.project_id) return;
    if (!hasProjectWrite.value) {
      Message.warning("缺少 project.write 权限，无法删除收件人");
      return;
    }
    await projectsApi.deleteRecipient(run.value.project_id, row.id);
    selectedEmails.value = selectedEmails.value.filter((email) => email !== row.email);
    await loadRecipients({ autoSelect: false });
    Message.success("收件人已删除");
  });

const toggleRecipientEmail = (email: string, checked: boolean | (string | number | boolean)[]) => {
  const on = checked === true;
  if (on) {
    if (!selectedEmails.value.includes(email)) {
      selectedEmails.value = [...selectedEmails.value, email];
    }
    return;
  }
  selectedEmails.value = selectedEmails.value.filter((item) => item !== email);
};

const confirmSendEmail = async () => {
  sendLoading.value = true;
  try {
    const extra = parseExtraEmails(extraEmailsText.value);
    const picked = selectedEmails.value.map((e) => e.trim().toLowerCase()).filter(Boolean);
    const want = Array.from(new Set([...picked, ...extra]));
    if (!want.length) {
      Message.warning("请至少选择一位收件人，或填写临时邮箱");
      return false;
    }
    emailResult.value = await runsApi.sendReport(runId.value, {
      emails: want,
      save_recipients: saveRecipients.value && extra.length > 0,
    });
    if (emailResult.value.ok && emailResult.value.mode === "smtp") {
      Message.success(`报告已发送给 ${emailResult.value.sent_to.join(", ")}`);
      return true;
    }
    if (emailResult.value.mode === "outbox" || emailResult.value.skipped) {
      Message.warning(
        emailResult.value.reason ||
          "未配置 SMTP，报告仅写入本地发件箱，收件人不会收到邮件。请到「平台配置」填写 SMTP。",
      );
      return true;
    }
    Message.warning(emailResult.value.reason || "邮件未发送");
    return false;
  } catch (error) {
    Message.error(error instanceof Error ? error.message : String(error));
    return false;
  } finally {
    sendLoading.value = false;
  }
};

const openReportNewTab = () => {
  const token = authStore.getToken();
  const url = `${API_BASE_URL}/runs/${runId.value}/reports/html`;
  if (token) {
    void fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.text())
      .then((html) => {
        const w = window.open("", "_blank");
        if (w) {
          w.document.write(html);
          w.document.close();
        }
      });
  }
};

const goTasks = () => {
  void router.push({ name: "tasks" });
};

const goProject = () => {
  if (run.value?.project_id) {
    void router.push({ name: "project-reports", params: { id: run.value.project_id } });
  }
};

const goSettings = () => {
  void router.push({ name: "settings" });
};

const goIntegrations = () => {
  if (run.value?.project_id) {
    void router.push({ name: "project-integrations", params: { id: run.value.project_id } });
  }
};

onMounted(() => {
  void manualRefresh();
});
</script>

<template>
  <div class="ai-workspace">
    <AiWorkspaceHero
      :title="`Run #${runId}`"
      subtitle="执行项、队列任务与报告闭环 — 实时追踪智能流水执行脉搏"
      badge="AI · RUN DETAIL"
      :status-label="isActiveRun ? '执行中' : statusLabel(run?.status || '加载中')"
      :status-tone="isActiveRun ? 'busy' : run?.status === 'failed' ? 'offline' : 'online'"
    >
      <template #extra>
        <div class="run-hero-actions">
          <a-switch
            v-model="autoRefresh"
            class="run-hero-actions__switch"
            checked-text="自动刷新"
            unchecked-text="暂停"
          />
          <div class="run-hero-actions__btns">
            <a-button :loading="pageLoading || polling" @click="manualRefresh">刷新</a-button>
            <a-button v-if="fromTasksCenter" @click="goTasks">返回任务中心</a-button>
            <a-button v-if="run?.project_id" @click="goProject">返回项目</a-button>
          </div>
        </div>
      </template>
    </AiWorkspaceHero>

    <a-spin :loading="pageLoading || polling">
      <a-descriptions v-if="run" :column="3" bordered class="mb-4 ai-panel">
        <a-descriptions-item label="项目 ID">{{ run.project_id }}</a-descriptions-item>
        <a-descriptions-item label="Run 状态">
          <a-tag :color="statusColor(run.status)">{{ statusLabel(run.status) }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="队列任务">
          <a-tag>{{ jobStatus }}</a-tag>
          <span v-if="run.execution_job?.cancel_requested" class="ml-2 text-orange">取消中</span>
        </a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ run.created_at }}</a-descriptions-item>
        <a-descriptions-item label="完成时间">{{ run.completed_at || "—" }}</a-descriptions-item>
        <a-descriptions-item label="尝试次数">
          {{ run.execution_job ? `${run.execution_job.attempt_count}/${run.execution_job.max_attempts}` : "—" }}
        </a-descriptions-item>
        <a-descriptions-item v-if="run.error_message" label="错误" :span="3">
          {{ run.error_message }}
        </a-descriptions-item>
        <a-descriptions-item v-if="run.execution_job?.last_error" label="任务错误" :span="3">
          {{ run.execution_job.last_error }}
        </a-descriptions-item>
      </a-descriptions>

      <a-space v-if="run" class="mb-4" wrap>
        <a-button
          v-if="hasRunExecute && ['pending', 'running'].includes(run.status)"
          status="warning"
          @click="cancelRun"
        >
          取消 Run
        </a-button>
        <a-button
          v-if="hasRunExecute && ['failed', 'cancelled', 'completed'].includes(run.status)"
          type="primary"
          class="ai-action-btn"
          @click="retryRun"
        >
          重试
        </a-button>
        <a-button v-if="hasReportRead" @click="generateReport">生成报告</a-button>
        <a-button v-if="hasReportRead" @click="openReportNewTab">新窗口预览</a-button>
        <a-button
          v-if="hasReportSend"
          type="primary"
          class="ai-action-btn"
          :disabled="isActiveRun"
          @click="openSendModal"
        >
          发送邮件
        </a-button>
      </a-space>

      <a-alert
        v-if="emailResult"
        class="mb-4"
        :type="emailAlertType"
        :title="emailAlertTitle"
        closable
        @close="emailResult = null"
      >
        <template v-if="emailResult.ok || emailResult.mode === 'outbox'">
          收件人：{{ emailResult.sent_to.join(", ") }}
          <div v-if="emailResult.reason" style="margin-top: 4px">{{ emailResult.reason }}</div>
          <div v-if="emailResult.outbox_path" style="margin-top: 4px; word-break: break-all">
            发件箱文件：{{ emailResult.outbox_path }}
          </div>
          <a-button
            v-if="emailResult.mode === 'outbox' && hasSettingsRead"
            type="text"
            size="mini"
            style="padding-left: 0"
            @click="goSettings"
          >
            去配置 SMTP
          </a-button>
        </template>
        <template v-else>
          {{ emailResult.reason || "发送失败" }}
          <a-button
            v-if="(emailResult.reason || '').includes('收件人')"
            type="text"
            size="mini"
            @click="openSendModal"
          >
            立即配置
          </a-button>
        </template>
      </a-alert>

      <a-alert
        v-if="allItemsSkipped"
        class="mb-4"
        type="warning"
        title="本次 Run 全部测试项已跳过"
        show-icon
      >
        常见原因：Docker 镜像未安装 k6/Playwright/扫描器，或目标地址不可达。报告仅说明环境问题，不代表业务测试通过。
      </a-alert>

      <a-card title="执行项" class="mb-4 ai-panel">
        <a-table :data="run?.items || []" :columns="itemColumns" row-key="id" :pagination="false">
          <template #status="{ record }">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template #reason="{ record }">
            <span class="run-item-reason">{{ itemReason(record) || "—" }}</span>
          </template>
          <template #detail="{ record }">
            <a-space>
              <a-button v-if="record.detail" size="mini" type="outline" @click="openItemDetail(record)">
                JSON
              </a-button>
              <a-button
                v-if="securityJobId(record)"
                size="mini"
                type="primary"
                @click="openSecurityReport(securityJobId(record)!)"
              >
                安全报告
              </a-button>
              <span v-if="!record.detail && !securityJobId(record)">—</span>
            </a-space>
          </template>
        </a-table>
      </a-card>

      <a-card v-if="hasReportRead && reportHtml" title="报告 HTML 预览" class="ai-panel">
        <iframe class="report-preview-frame" :srcdoc="reportHtml" title="report preview" />
      </a-card>

      <a-collapse v-if="run?.items?.length" class="mt-4 ai-panel run-log-collapse">
        <a-collapse-item v-for="item in run.items" :key="item.id" :header="`${item.kind} — stdout/stderr`">
          <div class="ai-log-block">
            <div v-if="item.stdout" class="ai-log-block__section">
              <div class="ai-log-block__label">
                <span>stdout</span>
                <a-typography-text copyable :copy-text="item.stdout">复制</a-typography-text>
              </div>
              <pre class="ai-payload ai-log-stream">{{ item.stdout }}</pre>
            </div>
            <div v-if="item.stderr" class="ai-log-block__section">
              <div class="ai-log-block__label ai-log-block__label--error">
                <span>stderr</span>
                <a-typography-text copyable :copy-text="item.stderr">复制</a-typography-text>
              </div>
              <pre class="ai-payload ai-log-stream ai-log-stream--error">{{ item.stderr }}</pre>
            </div>
            <div v-if="!item.stdout && !item.stderr" class="ai-empty" style="padding: 16px">
              <p class="ai-empty__title">暂无输出</p>
              <p class="ai-empty__desc">该执行项没有 stdout / stderr 日志。</p>
            </div>
          </div>
        </a-collapse-item>
      </a-collapse>
    </a-spin>

    <a-modal
      v-model:visible="sendVisible"
      title="发送测试报告"
      :ok-loading="sendLoading"
      ok-text="确认发送"
      unmount-on-close
      width="560px"
      :on-before-ok="confirmSendEmail"
    >
      <div class="send-modal">
        <div class="ai-chip-rail">
          <span class="ai-chip ai-chip--live">Report Mail</span>
          <span class="ai-chip">Run #{{ runId }}</span>
        </div>
        <a-typography-paragraph type="secondary" style="margin-bottom: 12px">
          将当前 HTML 报告发送给项目收件人。真实投递需先配置 SMTP；未配置时仅写入本地发件箱。
        </a-typography-paragraph>
        <a-alert
          v-if="mailStatus"
          :type="mailStatus.warning ? 'warning' : mailStatus.configured ? 'success' : 'warning'"
          show-icon
          style="margin-bottom: 12px"
          :title="
            mailStatus.warning
              ? 'SMTP 配置有误，发送会失败'
              : mailStatus.configured
                ? `SMTP 已就绪（${mailStatus.host || '已配置'}）`
                : '当前不会投递到真实邮箱'
          "
        >
          {{ mailStatus.hint }}
          <a-button
            v-if="(!mailStatus.configured || mailStatus.warning) && hasSettingsRead"
            type="text"
            size="mini"
            style="padding-left: 0"
            @click="goSettings"
          >
            打开平台配置
          </a-button>
        </a-alert>

        <div class="ai-field">
          <div class="ai-field__label">项目收件人</div>
          <div v-if="!recipients.length" class="ai-empty" style="padding: 16px">
            <p class="ai-empty__title">暂无收件人</p>
            <p class="ai-empty__desc">可在下方添加，或填写临时邮箱后直接发送。</p>
            <a-button v-if="run?.project_id" size="mini" type="outline" @click="goIntegrations">
              去项目集成页管理
            </a-button>
          </div>
          <div v-else class="recipient-list">
            <div v-for="row in recipients" :key="row.id" class="recipient-list__row">
              <a-checkbox
                :model-value="selectedEmails.includes(row.email)"
                @change="(checked) => toggleRecipientEmail(row.email, checked)"
              >
                {{ row.email }}
                <span v-if="row.display_name" class="recipient-list__name">（{{ row.display_name }}）</span>
              </a-checkbox>
              <a-popconfirm
                v-if="hasProjectWrite"
                content="确定删除该收件人？"
                @ok="removeRecipient(row)"
              >
                <a-button type="text" size="mini" status="danger">删除</a-button>
              </a-popconfirm>
            </div>
          </div>
        </div>

        <div class="ai-field">
          <div class="ai-field__label">快速添加收件人</div>
          <a-space wrap>
            <a-input v-model="newEmail" placeholder="qa@example.com" style="width: 220px" allow-clear />
            <a-input v-model="newDisplayName" placeholder="显示名（可选）" style="width: 140px" allow-clear />
            <a-button type="outline" :loading="store.loading.value" @click="addRecipientQuick">添加</a-button>
          </a-space>
        </div>

        <div class="ai-field">
          <div class="ai-field__label">临时邮箱（逗号/空格分隔）</div>
          <a-textarea
            v-model="extraEmailsText"
            :auto-size="{ minRows: 2, maxRows: 4 }"
            placeholder="例如：lead@example.com, pm@example.com"
          />
          <a-checkbox v-model="saveRecipients" style="margin-top: 8px">
            将临时邮箱同时保存为项目收件人
          </a-checkbox>
        </div>
      </div>
    </a-modal>
    <a-modal
      v-model:visible="detailVisible"
      :title="detailTitle"
      :footer="false"
      unmount-on-close
      width="720px"
      :body-style="{ paddingTop: '12px' }"
    >
      <div class="detail-modal">
        <div class="detail-modal__toolbar">
          <a-typography-text type="secondary">结构化执行详情（可复制）</a-typography-text>
          <a-typography-text copyable :copy-text="detailJsonText">复制 JSON</a-typography-text>
        </div>
        <pre class="run-detail-json ai-payload">{{ detailJsonText }}</pre>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.run-hero-actions {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.run-hero-actions__btns {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
}

.run-hero-actions__btns :deep(.arco-btn) {
  height: 32px;
  padding: 0 16px;
  line-height: 32px;
  margin: 0;
  flex: 0 0 auto;
}

.run-hero-actions__switch {
  flex: 0 0 auto;
  width: auto !important;
  min-width: 88px;
  height: 32px;
  line-height: 32px;
  margin: 0;
  border-radius: 16px;
  vertical-align: middle;
}

.run-hero-actions__switch :deep(.arco-switch-handle) {
  top: 4px;
  left: 4px;
  width: 24px;
  height: 24px;
}

.run-hero-actions__switch.arco-switch-checked :deep(.arco-switch-handle),
.run-hero-actions :deep(.run-hero-actions__switch.arco-switch-checked .arco-switch-handle) {
  left: calc(100% - 28px);
}

.run-hero-actions :deep(.run-hero-actions__switch .arco-switch-text-holder) {
  margin: 0 10px 0 32px;
  font-size: 13px;
  line-height: 32px;
}

.run-hero-actions :deep(.run-hero-actions__switch.arco-switch-checked .arco-switch-text-holder) {
  margin: 0 32px 0 10px;
}

.run-hero-actions :deep(.run-hero-actions__switch .arco-switch-text) {
  left: 32px;
  font-size: 13px;
  line-height: 32px;
}

.run-hero-actions :deep(.run-hero-actions__switch.arco-switch-checked .arco-switch-text) {
  left: 10px;
}

.report-preview-frame {
  width: 100%;
  min-height: 480px;
  border: 1px solid var(--color-border-2);
  border-radius: 4px;
}
.detail-modal__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.run-detail-json {
  width: 100%;
  max-height: min(60vh, 520px);
  overflow: auto;
  margin: 0;
  padding: 14px 16px;
  font-size: 12.5px;
  line-height: 1.55;
  border-radius: 10px;
  box-sizing: border-box;
}
.run-item-reason {
  font-size: 12px;
  color: var(--color-text-2);
}
.run-log-collapse :deep(.arco-typography) {
  margin-bottom: 0;
}
.send-modal .ai-field {
  margin-top: 14px;
}
.recipient-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.recipient-list__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 32px;
}
.recipient-list__name {
  color: var(--color-text-3);
}
.mb-4 {
  margin-bottom: 16px;
}
.mt-4 {
  margin-top: 16px;
}
</style>
