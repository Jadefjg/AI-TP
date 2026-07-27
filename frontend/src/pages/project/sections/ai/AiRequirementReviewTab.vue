<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { aiApi } from "../../../../api/ai";
import { useProjectAiContext } from "./useProjectAiContext";
import { resolveUploadFile, stubArcoUploadRequest } from "../../../../utils/manualUpload";

const router = useRouter();
const { projectId, store, aiForm, hasAiRead } = useProjectAiContext();

const requirementReviews = ref<
  Array<{
    id: number;
    model_name: string;
    created_at: string;
    source_filename?: string | null;
    source_format?: string | null;
    result_json: Record<string, unknown>;
  }>
>([]);
const reviewDiff = ref<Record<string, unknown> | null>(null);
const reviewDiffFrom = ref("");
const reviewDiffTo = ref("");
const uploadFileList = ref<Array<{ uid: string; name?: string; file?: File }>>([]);

const loadRequirementReviews = () =>
  store.runBackground(async () => {
    if (!hasAiRead.value) return;
    requirementReviews.value = await aiApi.listRequirementReviews(projectId.value);
  });

void loadRequirementReviews();

watch([() => store.authReady.value, () => store.currentUser.value, projectId], () => {
  void loadRequirementReviews();
});

const aiRequirementReview = () =>
  store.wrap(async () => {
    const result = await aiApi.aiRequirementReview(projectId.value, aiForm.requirementText);
    store.setOut(result);
    await loadRequirementReviews();
  });

const downloadReviewPdf = (reviewId: number) =>
  store.wrap(async () => {
    await aiApi.downloadRequirementReviewPdf(projectId.value, reviewId);
    store.setOut({ ok: true, reviewId });
  });

const previewReviewHtml = (reviewId: number) => {
  aiApi.openRequirementReviewHtml(projectId.value, reviewId);
};

const parseUploadedDocument = () =>
  store.wrap(async () => {
    const file = resolveUploadFile(uploadFileList.value[0]);
    if (!file) return;
    const parsed = await aiApi.parseRequirementDocument(projectId.value, file);
    aiForm.requirementText = parsed.text;
    store.setOut(parsed);
  });

const reviewFromUpload = () =>
  store.wrap(async () => {
    const file = resolveUploadFile(uploadFileList.value[0]);
    if (!file) return;
    const result = await aiApi.aiRequirementReviewUpload(projectId.value, file);
    store.setOut(result);
    await loadRequirementReviews();
  });

const convertReviewToCases = (reviewId: number) =>
  store.wrap(async () => {
    const result = await aiApi.convertReviewToCases(projectId.value, reviewId);
    store.setOut(result);
    void router.push({ name: "project-cases", params: { id: String(projectId.value) } });
  });

const loadReviewDiff = () =>
  store.wrap(async () => {
    const fromId = Number(reviewDiffFrom.value);
    const toId = Number(reviewDiffTo.value);
    if (!fromId || !toId) return;
    reviewDiff.value = await aiApi.diffRequirementReviews(projectId.value, fromId, toId);
    store.setOut(reviewDiff.value);
  });
</script>

<template>
  <a-typography-text type="secondary">支持粘贴文本，或上传 Word(.docx) / PDF / Markdown / TXT</a-typography-text>
  <a-upload
    v-model:file-list="uploadFileList"
    :auto-upload="false"
    :custom-request="stubArcoUploadRequest"
    :show-retry-button="false"
    :limit="1"
    accept=".docx,.pdf,.md,.markdown,.txt"
    style="margin: 8px 0"
  />
  <a-space wrap>
    <a-button @click="parseUploadedDocument">解析文档到文本框</a-button>
    <a-button type="primary" @click="reviewFromUpload">上传并评审</a-button>
  </a-space>
  <a-textarea v-model="aiForm.requirementText" :auto-size="{ minRows: 4 }" placeholder="需求原文" />
  <a-button type="outline" style="margin-top: 8px" @click="aiRequirementReview">文本评审</a-button>

  <a-list v-if="requirementReviews.length" :data="requirementReviews" style="margin-top: 12px">
    <template #item="{ item }">
      <a-list-item>
        <a-list-item-meta
          :title="`评审 #${item.id} · ${item.model_name}`"
          :description="`${item.source_filename || '粘贴文本'} · ${item.created_at}`"
        />
        <template #actions>
          <a-button size="mini" @click="previewReviewHtml(item.id)">HTML 预览</a-button>
          <a-button size="mini" @click="downloadReviewPdf(item.id)">PDF</a-button>
          <a-button size="mini" type="primary" @click="convertReviewToCases(item.id)">一键转用例</a-button>
        </template>
      </a-list-item>
    </template>
  </a-list>

  <a-card v-if="requirementReviews.length >= 2" title="版本对比 (diff)" size="small" style="margin-top: 12px">
    <a-space>
      <a-input v-model="reviewDiffFrom" placeholder="旧版本 ID" style="width: 120px" />
      <a-input v-model="reviewDiffTo" placeholder="新版本 ID" style="width: 120px" />
      <a-button @click="loadReviewDiff">对比</a-button>
    </a-space>
    <pre v-if="reviewDiff" class="payload-pre">{{ JSON.stringify(reviewDiff, null, 2) }}</pre>
  </a-card>
</template>
