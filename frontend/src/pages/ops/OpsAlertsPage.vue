<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { opsApi, type OpsOverview } from "../../api/ops";
import { usePlatformStore } from "../../state/platform";

const store = usePlatformStore();
const router = useRouter();
const overview = ref<OpsOverview | null>(null);

const channels = computed(() => overview.value?.alert_channels ?? {});

const load = () =>
  store.wrap(async () => {
    overview.value = await opsApi.overview();
  });

onMounted(() => {
  void load();
});
</script>

<template>
  <div>
    <a-alert
      type="warning"
      show-icon
      style="margin-bottom: 16px"
      title="告警通道密钥在系统配置中维护；本页仅展示可观测状态，不暴露密钥。"
    />
    <a-card title="通道概览" class="ai-panel" size="small">
      <a-descriptions :column="1" bordered size="small" v-if="overview">
        <a-descriptions-item label="Run 失败告警">
          {{ channels.run_failure_alert_enabled ? "已启用" : "未启用" }}
        </a-descriptions-item>
        <a-descriptions-item label="渠道串">{{ channels.channels || "—" }}</a-descriptions-item>
        <a-descriptions-item label="钉钉">{{ channels.dingtalk_configured ? "已配置" : "未配置" }}</a-descriptions-item>
        <a-descriptions-item label="企业微信">{{ channels.wecom_configured ? "已配置" : "未配置" }}</a-descriptions-item>
        <a-descriptions-item label="通用 Webhook">
          {{ channels.generic_webhook_configured ? "已配置" : "未配置" }}
        </a-descriptions-item>
        <a-descriptions-item label="Metrics 鉴权">
          {{ channels.metrics_auth_enabled ? "已启用" : "未启用" }}
        </a-descriptions-item>
      </a-descriptions>
      <a-space style="margin-top: 16px">
        <a-button type="primary" class="ai-action-btn" @click="() => router.push({ name: 'settings' })">
          前往系统配置
        </a-button>
        <a-button @click="load">刷新状态</a-button>
      </a-space>
    </a-card>
  </div>
</template>
