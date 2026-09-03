<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { aiApi } from "../../api/ai";

const props = withDefaults(
  defineProps<{
    agentKey?: "requirement" | "ui" | "interface" | "perf" | "security";
  }>(),
  { agentKey: undefined },
);

type PipelineStatus = Awaited<ReturnType<typeof aiApi.getPipelineStatus>>;

const status = ref<PipelineStatus | null>(null);
const loadError = ref("");

const agent = computed(() => {
  if (!props.agentKey || !status.value) return null;
  return status.value.agents.find((item) => item.key === props.agentKey) || null;
});

const alerts = computed(() => {
  const items: Array<{ type: "warning" | "info"; title: string }> = [];
  if (!status.value) return items;
  const llm = status.value.llm;
  if (!llm.configured) {
    items.push({
      type: "warning",
      title:
        "未配置 LLM Key：生成将走本地/Stub 兜底，质量有限。请在系统配置或环境变量中设置 DeepSeek/OpenAI Key。",
    });
  }
  if (agent.value && !agent.value.execute_ready) {
    items.push({
      type: "warning",
      title: `${agent.value.label} 执行环境未就绪：${agent.value.hint || "工具缺失时任务将 skipped"}`,
    });
  } else if (agent.value && !agent.value.generate_ready) {
    items.push({
      type: "warning",
      title: `${agent.value.label} 生成能力未就绪：${agent.value.hint || "请检查配置"}`,
    });
  }
  return items;
});

onMounted(async () => {
  try {
    status.value = await aiApi.getPipelineStatus();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  }
});
</script>

<template>
  <div v-if="loadError || alerts.length" class="agent-ready">
    <a-alert v-if="loadError" type="error" show-icon :title="`就绪状态获取失败：${loadError}`" />
    <a-alert
      v-for="(item, index) in alerts"
      :key="`${item.type}-${index}`"
      :type="item.type"
      show-icon
      :title="item.title"
    />
  </div>
</template>

<style scoped>
.agent-ready {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
}
</style>
