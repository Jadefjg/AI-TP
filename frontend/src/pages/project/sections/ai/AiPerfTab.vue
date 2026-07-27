<script setup lang="ts">
import { ref } from "vue";
import { aiApi } from "../../../../api/ai";
import { useProjectAiContext } from "./useProjectAiContext";

const { projectId, store, aiForm, hasAiExecute, perfK6Jobs, selectedPerfJobId, loadAiArtifacts, loadPerfK6Jobs } =
  useProjectAiContext();

const perfMonitor = ref<Record<string, unknown> | null>(null);

const aiPerfPlan = () =>
  store.wrap(async () => {
    const result = await aiApi.aiPerfPlan(projectId.value, {
      biz_desc: aiForm.bizDesc,
      api_doc: aiForm.apiDoc,
    });
    store.setOut(result);
    await loadAiArtifacts();
  });

const loadPerfMonitor = () =>
  store.wrap(async () => {
    const jobId = Number(selectedPerfJobId.value);
    if (!jobId) return;
    perfMonitor.value = await aiApi.getPerfMonitor(projectId.value, jobId);
    store.setOut(perfMonitor.value);
  });

const analyzePerfBottleneck = () =>
  store.wrap(async () => {
    const jobId = Number(selectedPerfJobId.value);
    if (!jobId) return;
    const result = await aiApi.analyzePerfBottleneck(projectId.value, jobId);
    store.setOut(result);
    await loadPerfMonitor();
  });
</script>

<template>
  <a-textarea v-model="aiForm.bizDesc" placeholder="业务描述" :auto-size="{ minRows: 2 }" />
  <a-textarea
    v-model="aiForm.apiDoc"
    placeholder="接口文档（可选）"
    :auto-size="{ minRows: 2 }"
    style="margin-top: 8px"
  />
  <a-checkbox v-model="aiForm.perfDistributed" style="margin-top: 8px">
    分布式 k6（execution segment 分片）
  </a-checkbox>
  <a-button type="primary" style="margin-top: 8px" @click="aiPerfPlan">生成方案</a-button>

  <a-divider orientation="left">实时监控</a-divider>
  <a-space>
    <a-select v-model="selectedPerfJobId" placeholder="k6 Job" style="width: 200px" allow-clear>
      <a-option v-for="j in perfK6Jobs" :key="String(j.id)" :value="String(j.id)">
        Job #{{ j.id }} · {{ j.status }}
      </a-option>
    </a-select>
    <a-button @click="loadPerfMonitor">加载曲线</a-button>
    <a-button @click="loadPerfK6Jobs">刷新 Jobs</a-button>
    <a-button v-if="hasAiExecute" type="outline" @click="analyzePerfBottleneck">AI 瓶颈分析</a-button>
  </a-space>
  <a-row v-if="perfMonitor?.summary_metrics" :gutter="12" style="margin-top: 12px">
    <a-col :span="6">
      <a-statistic
        title="P95 RT(ms)"
        :value="Number((perfMonitor.summary_metrics as Record<string, unknown>).p95_rt_ms || 0)"
      />
    </a-col>
    <a-col :span="6">
      <a-statistic
        title="TPS"
        :value="Number((perfMonitor.summary_metrics as Record<string, unknown>).tps || 0)"
      />
    </a-col>
    <a-col :span="6">
      <a-statistic
        title="错误率%"
        :value="Number((perfMonitor.summary_metrics as Record<string, unknown>).error_rate || 0)"
      />
    </a-col>
    <a-col :span="6">
      <a-statistic
        title="请求数"
        :value="Number((perfMonitor.summary_metrics as Record<string, unknown>).http_reqs || 0)"
      />
    </a-col>
  </a-row>
  <a-typography-text
    v-if="(perfMonitor?.time_series as unknown[] | undefined)?.length"
    type="secondary"
    style="display: block; margin-top: 8px"
  >
    曲线基于汇总指标估算（非 k6 实时流）；完整指标见 summary_metrics
  </a-typography-text>
  <div v-if="(perfMonitor?.time_series as unknown[] | undefined)?.length" class="monitor-chart">
    <div
      v-for="(p, i) in perfMonitor?.time_series as Array<{ t_sec: number; rt_ms: number; tps: number }>"
      :key="i"
      class="monitor-bar"
      :title="`t=${p.t_sec}s RT=${p.rt_ms} TPS=${p.tps}`"
      :style="{ height: `${Math.min(120, (p.rt_ms || 0) / 3)}px` }"
    />
  </div>
  <pre v-if="perfMonitor?.bottleneck_analysis" class="payload-pre">{{
    JSON.stringify(perfMonitor.bottleneck_analysis, null, 2)
  }}</pre>
</template>
