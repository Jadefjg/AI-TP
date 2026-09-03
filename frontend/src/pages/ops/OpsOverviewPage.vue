<script setup lang="ts">
import { onMounted, ref } from "vue";
import { opsApi, type OpsOverview } from "../../api/ops";
import { usePlatformStore } from "../../state/platform";

const store = usePlatformStore();
const overview = ref<OpsOverview | null>(null);

const load = () =>
  store.wrap(async () => {
    overview.value = await opsApi.overview();
  });

onMounted(() => {
  void load();
});
</script>

<template>
  <div v-if="overview" class="ops-overview">
    <a-card title="运维工作流" class="ai-panel ai-guide-rail">
      <div class="ai-guide-rail__row">
        <div class="ai-guide ai-guide--horizontal">
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">01</span>
            <div>
              <div class="ai-guide-step__title">观察健康</div>
              <div class="ai-guide-step__desc">看评分、队列积压与 Worker 在线情况</div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">02</span>
            <div>
              <div class="ai-guide-step__title">管控调度</div>
              <div class="ai-guide-step__desc">白名单定时任务与 k6 节点启停</div>
            </div>
          </div>
          <div class="ai-guide-step">
            <span class="ai-guide-step__no">03</span>
            <div>
              <div class="ai-guide-step__title">追溯告警</div>
              <div class="ai-guide-step__desc">通道状态与审计日志可下钻核对</div>
            </div>
          </div>
        </div>
        <div class="ai-next-hint">
          <p class="ai-next-hint__title">Next · 运维提示</p>
          <p class="ai-next-hint__desc">
            队列积压或健康分偏低时，先看告警通道是否开启，再到定时任务核对最近一次执行；压测节点异常请进入 06 k6 节点探活。
          </p>
        </div>
      </div>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="6">
        <a-card class="metric ai-panel" size="small">
          <div class="metric__label">健康评分</div>
          <div class="metric__value">{{ overview.health_score }}</div>
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card class="metric ai-panel" size="small">
          <div class="metric__label">执行队列 pending</div>
          <div class="metric__value">{{ overview.queue.execution_pending }}</div>
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card class="metric ai-panel" size="small">
          <div class="metric__label">AI 队列 pending</div>
          <div class="metric__value">{{ overview.queue.ai_pending }}</div>
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card class="metric ai-panel" size="small">
          <div class="metric__label">定时任务启用</div>
          <div class="metric__value">{{ overview.scheduled_jobs.enabled }}/{{ overview.scheduled_jobs.total }}</div>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="16" style="margin-top: 16px">
      <a-col :span="12">
        <a-card title="队列与 Worker" class="ai-panel" size="small">
          <p>队列后端：{{ overview.queue.backend }}</p>
          <p>执行中：exec={{ overview.queue.execution_running }} · ai={{ overview.queue.ai_running }}</p>
          <p>k6 节点：{{ overview.workers.enabled }}/{{ overview.workers.total }} 启用</p>
          <p>配置项 / 审计条数：{{ overview.settings_count }} / {{ overview.audit_count }}</p>
          <p>API 版本：{{ overview.api_version }}</p>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card title="告警通道状态" class="ai-panel" size="small">
          <a-space wrap>
            <a-tag :color="overview.alert_channels.run_failure_alert_enabled ? 'green' : 'red'">
              Run 失败告警 {{ overview.alert_channels.run_failure_alert_enabled ? "开" : "关" }}
            </a-tag>
            <a-tag :color="overview.alert_channels.dingtalk_configured ? 'arcoblue' : 'gray'">钉钉</a-tag>
            <a-tag :color="overview.alert_channels.wecom_configured ? 'arcoblue' : 'gray'">企微</a-tag>
            <a-tag :color="overview.alert_channels.generic_webhook_configured ? 'arcoblue' : 'gray'">Webhook</a-tag>
            <a-tag :color="overview.alert_channels.metrics_auth_enabled ? 'green' : 'orangered'">
              Metrics Auth
            </a-tag>
          </a-space>
          <p style="margin-top: 10px; color: #64748b">通道：{{ overview.alert_channels.channels || "—" }}</p>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="最近告警 / 异常审计" class="ai-panel" size="small" style="margin-top: 16px">
      <a-table
        :data="overview.recent_alerts"
        :pagination="false"
        row-key="id"
        :columns="[
          { title: '级别', dataIndex: 'level', width: 90 },
          { title: '模块', dataIndex: 'module', width: 120 },
          { title: '动作', dataIndex: 'action', width: 160 },
          { title: '消息', dataIndex: 'message', ellipsis: true },
          { title: '时间', dataIndex: 'created_at', width: 180 },
        ]"
      />
    </a-card>
  </div>
  <a-empty v-else description="加载中或暂无数据" class="ai-empty" />
</template>

<style scoped>
.metric__label {
  color: #64748b;
  font-size: 12px;
}
.metric__value {
  margin-top: 6px;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}
</style>
