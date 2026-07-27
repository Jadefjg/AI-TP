<script setup lang="ts">
import { aiApi } from "../../../../api/ai";
import { useProjectAiContext } from "./useProjectAiContext";

const { projectId, store, aiForm, loadAiArtifacts } = useProjectAiContext();

const aiSecurityScan = () =>
  store.wrap(async () => {
    const result = await aiApi.aiSecurityScan(projectId.value, aiForm.apiParams);
    store.setOut(result);
    await loadAiArtifacts();
  });
</script>

<template>
  <a-textarea v-model="aiForm.apiParams" placeholder="接口入参" :auto-size="{ minRows: 2 }" />
  <a-button type="primary" @click="aiSecurityScan">生成 Payload</a-button>
  <a-select v-model="aiForm.securityEngine" style="width: 220px; margin-top: 8px">
    <a-option value="builtin">内置启发式</a-option>
    <a-option value="nuclei">nuclei</a-option>
    <a-option value="zap">OWASP ZAP</a-option>
    <a-option value="combined">combined（nuclei + 内置）</a-option>
  </a-select>
  <a-divider />
  <a-input v-model="aiForm.targetUrl" placeholder="扫描目标 URL" />
  <a-row :gutter="8" style="margin-top: 8px">
    <a-col :span="8"><a-input v-model="aiForm.scanMethod" placeholder="GET" /></a-col>
    <a-col :span="8"><a-input v-model="aiForm.paramName" placeholder="参数名" /></a-col>
    <a-col :span="8"><a-input v-model="aiForm.paramValue" placeholder="基准值" /></a-col>
  </a-row>
  <a-typography-text type="secondary" style="display: block; margin-top: 8px">
    Run 环境：sec_backend/sec_frontend 可与 bandit/npm audit + AI 扫描合并（执行 Tab 配置 security_mode）
  </a-typography-text>
</template>
