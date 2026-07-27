<script setup lang="ts">
import { useRouter } from "vue-router";
import { aiApi } from "../../../../api/ai";
import { Message } from "@arco-design/web-vue";
import { useProjectAiContext } from "./useProjectAiContext";

const router = useRouter();
const { projectId, store, aiForm } = useProjectAiContext();

const aiFunctionalCases = () => {
  const text = aiForm.requirementText.trim();
  if (text.length < 10) {
    Message.warning("需求文本至少 10 个字符，请先在「需求预评审」中填写");
    return;
  }
  void store.wrap(async () => {
    const result = await aiApi.aiFunctionalCases(projectId.value, {
      requirement_text: text,
      openapi_content: aiForm.openapiContent,
    });
    store.setOut(result);
    void router.push({ name: "project-cases", params: { id: String(projectId.value) } });
  });
};
</script>

<template>
  <a-textarea
    v-model="aiForm.openapiContent"
    placeholder="OpenAPI 文档（可选）"
    :auto-size="{ minRows: 2 }"
    style="margin-bottom: 8px"
  />
  <a-typography-text type="secondary" style="display: block; margin-bottom: 8px">
    需求文本请在「需求预评审」中填写，将自动复用。
  </a-typography-text>
  <a-button type="primary" @click="aiFunctionalCases">生成并入库</a-button>
</template>
