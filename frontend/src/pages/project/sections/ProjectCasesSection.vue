<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { computed, onMounted, reactive, ref } from "vue";
import { casesApi } from "../../../api/cases";
import { projectsApi } from "../../../api/projects";
import { authStore } from "../../../api/auth-store";
import { listTablePagination } from "../../../constants/listPagination";
import { useProjectScope } from "../../../composables/useProjectScope";
import { usePlatformStore } from "../../../state/platform";
import type { FunctionalCase, TestPlan, TestSuite } from "../../../types";
import { stepsToText, textToSteps } from "./caseUtils";
import "../../../assets/project-section.css";

const store = usePlatformStore();
const { projectId } = useProjectScope();

const cases = ref<FunctionalCase[]>([]);
const knowledge = ref<Array<{ id: number; source: string; title: string | null; content: string }>>([]);
const contexts = ref<Array<Record<string, unknown>>>([]);
const kbForm = reactive({ source: "manual", title: "", content: "" });
const kbSearchQuery = ref("");
const kbSearchHits = ref<Array<{ id: number; title: string | null; content: string; score: number | null }>>([]);
const caseForm = reactive({ requirementText: "", openapiContent: "" });

const hasKnowledgeRead = computed(() => store.hasPermission("knowledge.read"));
const hasKnowledgeWrite = computed(() => store.hasPermission("knowledge.write"));
const hasCaseRead = computed(() => store.hasPermission("case.read"));
const hasCaseWrite = computed(() => store.hasPermission("case.write"));
const hasCaseGenerate = computed(() => store.hasPermission("case.generate"));

const caseSubTab = ref<"list" | "org" | "openapi">("list");
const caseEditVisible = ref(false);
const editingCaseId = ref<number | null>(null);
const caseEditForm = reactive({
  title: "",
  module: "",
  preconditions: "",
  stepsText: "",
  expected: "",
  priority: "medium",
});
const testPlans = ref<TestPlan[]>([]);
const testSuites = ref<TestSuite[]>([]);
const planForm = reactive({ name: "", description: "" });
const suiteForm = reactive({ name: "", description: "", planId: "" });
const suiteAssignVisible = ref(false);
const suiteAssignId = ref<number | null>(null);
const suiteAssignCaseIds = ref<number[]>([]);
const openapiPersist = ref(true);
const openapiBusy = ref(false);
const openapiPreview = ref<FunctionalCase[]>([]);
const caseImportInputRef = ref<HTMLInputElement | null>(null);

const SAMPLE_OPENAPI = `{
  "openapi": "3.0.3",
  "info": { "title": "Demo API", "version": "1.0.0" },
  "paths": {
    "/health": {
      "get": {
        "operationId": "getHealth",
        "summary": "健康检查",
        "tags": ["system"],
        "responses": { "200": { "description": "服务正常" } }
      }
    },
    "/users": {
      "post": {
        "operationId": "createUser",
        "summary": "创建用户",
        "tags": ["users"],
        "requestBody": { "required": true },
        "responses": { "201": { "description": "创建成功" } }
      }
    }
  }
}`;

const fillSampleOpenApi = () => {
  caseForm.openapiContent = SAMPLE_OPENAPI;
  Message.success("已填入示例 OpenAPI，可直接「解析并导入」");
};

const importOpenApi = () => {
  const content = caseForm.openapiContent.trim();
  if (!content) {
    Message.warning("请先粘贴 OpenAPI / Swagger 的 JSON 或 YAML");
    return;
  }
  if (content.length < 10) {
    Message.warning("内容过短：请粘贴完整 OpenAPI 文档（需包含 paths）");
    return;
  }
  if (!/["']?paths["']?\s*:/.test(content) && !content.includes("paths")) {
    Message.warning("未检测到 paths 字段，请确认粘贴的是 OpenAPI/Swagger 文档");
    return;
  }
  openapiBusy.value = true;
  void store
    .wrap(async () => {
      const result = await casesApi.importOpenApiCases(
        projectId.value,
        content,
        openapiPersist.value,
      );
      openapiPreview.value = result;
      if (openapiPersist.value && hasCaseRead.value) {
        await loadCases();
      }
      const verb = openapiPersist.value ? "已解析并导入" : "已解析（未入库）";
      Message.success(`${verb} ${result.length} 条用例骨架`);
      if (openapiPersist.value) {
        caseSubTab.value = "list";
      }
    })
    .finally(() => {
      openapiBusy.value = false;
    });
};
const importingCases = ref(false);
const generatingCases = ref(false);
const tablePagination = listTablePagination(10);

const caseColumns = [
  { title: "ID", dataIndex: "id", width: 70 },
  { title: "标题", dataIndex: "title", ellipsis: true },
  { title: "模块", dataIndex: "module", width: 120 },
  { title: "优先级", dataIndex: "priority", width: 90 },
  { title: "操作", slotName: "actions", width: 160 },
];

const loadKnowledge = () =>
  store.wrap(async () => {
    if (!hasKnowledgeRead.value) return;
    knowledge.value = await casesApi.listKnowledge(projectId.value);
  });

const loadCases = () =>
  store.wrap(async () => {
    if (!hasCaseRead.value) return;
    cases.value = await casesApi.listCases(projectId.value);
  });

const searchKnowledge = () =>
  store.wrap(async () => {
    if (!kbSearchQuery.value.trim()) return;
    const res = await casesApi.searchKnowledge(projectId.value, kbSearchQuery.value.trim());
    kbSearchHits.value = res.hits;
    store.setOut(res);
  });

const addKnowledge = () => {
  const content = kbForm.content.trim();
  const source = kbForm.source.trim() || "manual";
  if (!content) {
    Message.warning("请填写知识库正文内容");
    return;
  }
  void store.wrap(async () => {
    await casesApi.addKnowledge(projectId.value, {
      source,
      title: kbForm.title.trim() || null,
      content,
    });
    kbForm.title = "";
    kbForm.content = "";
    await loadKnowledge();
    Message.success("知识已入库");
  });
};

const MIN_REQUIREMENT_LEN = 10;

const validateRequirementText = () => {
  const text = caseForm.requirementText.trim();
  if (!text) {
    Message.warning("请填写需求内容");
    return null;
  }
  if (text.length < MIN_REQUIREMENT_LEN) {
    Message.warning(`需求内容至少 ${MIN_REQUIREMENT_LEN} 个字符`);
    return null;
  }
  return text;
};

const genCases = () => {
  const requirementText = validateRequirementText();
  if (!requirementText) return;
  generatingCases.value = true;
  void store
    .wrap(async () => {
      cases.value = await casesApi.genCases(projectId.value, requirementText);
      contexts.value = [];
      Message.success(`已生成 ${cases.value.length} 条用例`);
    })
    .finally(() => {
      generatingCases.value = false;
    });
};

const genCasesAgent = () => {
  const requirementText = validateRequirementText();
  if (!requirementText) return;
  generatingCases.value = true;
  void store
    .wrap(async () => {
      const result = await casesApi.genCasesAgent(projectId.value, requirementText);
      cases.value = result.cases;
      contexts.value = result.contexts;
      Message.success(`已生成 ${result.cases.length} 条用例（RAG 命中 ${result.contexts.length} 条）`);
    })
    .finally(() => {
      generatingCases.value = false;
    });
};

const openCreateCase = () => {
  editingCaseId.value = null;
  Object.assign(caseEditForm, {
    title: "",
    module: "",
    preconditions: "",
    stepsText: "",
    expected: "",
    priority: "medium",
  });
  caseEditVisible.value = true;
};

const openEditCase = (item: FunctionalCase) => {
  editingCaseId.value = item.id;
  caseEditForm.title = item.title;
  caseEditForm.module = item.module || "";
  caseEditForm.preconditions = item.preconditions || "";
  caseEditForm.stepsText = stepsToText(item.steps);
  caseEditForm.expected = item.expected || "";
  caseEditForm.priority = item.priority || "medium";
  caseEditVisible.value = true;
};

const saveCaseEdit = () =>
  store.wrap(async () => {
    const body = {
      title: caseEditForm.title,
      module: caseEditForm.module || null,
      preconditions: caseEditForm.preconditions || null,
      steps: textToSteps(caseEditForm.stepsText),
      expected: caseEditForm.expected || null,
      priority: caseEditForm.priority,
    };
    if (editingCaseId.value) {
      await casesApi.updateCase(projectId.value, editingCaseId.value, body);
    } else {
      await casesApi.createCase(projectId.value, body);
    }
    caseEditVisible.value = false;
    await loadCases();
  });

const removeCase = (caseId: number) =>
  store.wrap(async () => {
    await casesApi.deleteCase(projectId.value, caseId);
    await loadCases();
  });

const exportCasesJson = async () => {
  try {
    const token = authStore.getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(projectsApi.exportCasesUrl(projectId.value), { headers });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail || "导出失败");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cases-project-${projectId.value}.json`;
    a.click();
    URL.revokeObjectURL(url);
    Message.success("用例 JSON 已导出");
  } catch (error) {
    Message.error(error instanceof Error ? error.message : String(error));
  }
};

const normalizeImportRow = (row: Record<string, unknown>) => ({
  title: String(row.title || "").trim(),
  module: row.module != null ? String(row.module) : null,
  preconditions: row.preconditions != null ? String(row.preconditions) : null,
  steps: Array.isArray(row.steps) ? row.steps.map((step) => String(step)) : [],
  expected: row.expected != null ? String(row.expected) : null,
  priority: row.priority != null ? String(row.priority) : "medium",
  source_requirement: row.source_requirement != null ? String(row.source_requirement) : null,
  openapi_operation_id: row.openapi_operation_id != null ? String(row.openapi_operation_id) : null,
});

const openCaseImport = () => {
  caseImportInputRef.value?.click();
};

const importCasesFromFile = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;

  let parsed: unknown;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    Message.error("JSON 格式无效，请检查文件内容");
    return;
  }

  const rawRows = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === "object" && Array.isArray((parsed as { cases?: unknown }).cases)
      ? (parsed as { cases: Array<Record<string, unknown>> }).cases
      : [];

  if (!rawRows.length) {
    Message.warning('JSON 中未找到用例数据（支持 `{ "cases": [...] }` 或直接数组）');
    return;
  }

  const rows = rawRows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map(normalizeImportRow)
    .filter((row) => row.title);

  if (!rows.length) {
    Message.warning("未找到有效用例，每条记录须包含 title 字段");
    return;
  }

  importingCases.value = true;
  try {
    const created = await casesApi.importCases(projectId.value, rows);
    await loadCases();
    Message.success(`已导入 ${created.length} 条用例`);
  } catch (error) {
    Message.error(error instanceof Error ? error.message : String(error));
  } finally {
    importingCases.value = false;
  }
};

const loadTestOrg = () =>
  store.wrap(async () => {
    testPlans.value = await casesApi.listTestPlans(projectId.value);
    testSuites.value = await casesApi.listTestSuites(projectId.value);
  });

const createPlan = () =>
  store.wrap(async () => {
    await casesApi.createTestPlan(projectId.value, {
      name: planForm.name,
      description: planForm.description || null,
    });
    planForm.name = "";
    planForm.description = "";
    await loadTestOrg();
  });

const createSuite = () =>
  store.wrap(async () => {
    await casesApi.createTestSuite(projectId.value, {
      name: suiteForm.name,
      description: suiteForm.description || null,
      plan_id: suiteForm.planId ? Number(suiteForm.planId) : null,
    });
    suiteForm.name = "";
    suiteForm.description = "";
    await loadTestOrg();
  });

const openSuiteAssign = (suiteId: number) => {
  suiteAssignId.value = suiteId;
  suiteAssignCaseIds.value = [];
  suiteAssignVisible.value = true;
};

const saveSuiteAssign = () =>
  store.wrap(async () => {
    if (!suiteAssignId.value) return;
    await casesApi.assignSuiteCases(projectId.value, suiteAssignId.value, suiteAssignCaseIds.value);
    suiteAssignVisible.value = false;
    await loadTestOrg();
  });

onMounted(() => {
  if (hasKnowledgeRead.value) void loadKnowledge();
  if (hasCaseRead.value) {
    void loadCases();
    void loadTestOrg();
  }
});
</script>

<template>
  <div>
    <a-card title="知识库（向量 RAG）" class="ai-panel" style="margin-bottom: 16px">
      <div class="ai-chip-rail">
        <span class="ai-chip ai-chip--live">RAG</span>
        <span class="ai-chip">Embedding</span>
        <span class="ai-chip">{{ knowledge.length }} docs</span>
      </div>
      <a-form v-if="hasKnowledgeWrite" layout="vertical">
        <a-form-item label="来源">
          <a-input v-model="kbForm.source" placeholder="manual / PRD / Wiki" allow-clear />
        </a-form-item>
        <a-form-item label="标题">
          <a-input v-model="kbForm.title" placeholder="可选" allow-clear />
        </a-form-item>
        <a-form-item label="正文" required>
          <a-textarea
            v-model="kbForm.content"
            placeholder="粘贴需求说明、接口文档或测试要点"
            :auto-size="{ minRows: 4 }"
          />
        </a-form-item>
        <a-button type="primary" class="ai-action-btn" @click="addKnowledge">入库（自动 Embedding）</a-button>
      </a-form>
      <a-form v-if="hasKnowledgeRead" layout="inline" style="margin-top: 12px">
        <a-input v-model="kbSearchQuery" placeholder="向量检索 query" style="width: 320px" />
        <a-button type="outline" @click="searchKnowledge">检索</a-button>
      </a-form>
      <a-list v-if="kbSearchHits.length" :data="kbSearchHits" style="margin-top: 8px">
        <template #item="{ item }">
          <a-list-item-meta :title="item.title || `chunk #${item.id}`" :description="`score ${item.score ?? '-'}`" />
          <div>{{ item.content.slice(0, 240) }}</div>
        </template>
      </a-list>
      <div v-if="hasKnowledgeRead && !knowledge.length" class="ai-empty" style="margin-top: 12px">
        <p class="ai-empty__title">知识库为空</p>
        <p class="ai-empty__desc">入库 PRD / 接口说明后，Agent + RAG 生成用例时会自动引用。</p>
      </div>
      <a-list v-else-if="hasKnowledgeRead" :data="knowledge" style="margin-top: 12px">
        <template #item="{ item }">
          <a-list-item-meta :title="item.title || item.source" :description="item.source" />
          <div>{{ item.content }}</div>
        </template>
      </a-list>
    </a-card>

    <a-card title="功能用例" class="ai-panel ai-panel--accent">
      <div class="ai-chip-rail">
        <span class="ai-chip ai-chip--live">Cases</span>
        <span class="ai-chip">{{ cases.length }} items</span>
      </div>
      <a-tabs v-model:active-key="caseSubTab">
        <a-tab-pane key="list" title="用例列表">
          <a-space wrap style="margin-bottom: 12px">
            <a-button v-if="hasCaseRead" @click="loadCases">刷新</a-button>
            <a-button v-if="hasCaseWrite" type="primary" class="ai-action-btn" @click="openCreateCase">
              新建用例
            </a-button>
            <a-button v-if="hasCaseRead" @click="exportCasesJson">导出 JSON</a-button>
            <template v-if="hasCaseWrite">
              <input
                ref="caseImportInputRef"
                type="file"
                accept="application/json,.json"
                class="case-import-input"
                @change="importCasesFromFile"
              />
              <a-button :loading="importingCases" @click="openCaseImport">导入 JSON</a-button>
            </template>
          </a-space>
          <template v-if="hasCaseGenerate">
            <div class="ai-section-title">AI 生成</div>
            <a-form layout="vertical" class="case-ai-panel">
              <a-form-item label="需求内容" required>
                <a-textarea
                  v-model="caseForm.requirementText"
                  placeholder="描述功能需求、用户故事或验收标准（至少 10 个字符）"
                  :auto-size="{ minRows: 4 }"
                />
              </a-form-item>
              <a-space>
                <a-button :loading="generatingCases" @click="genCases">生成用例</a-button>
                <a-button
                  type="primary"
                  class="ai-action-btn"
                  :loading="generatingCases"
                  @click="genCasesAgent"
                >
                  Agent + RAG
                </a-button>
              </a-space>
            </a-form>
            <a-alert v-if="contexts.length" type="info" style="margin-top: 8px">
              RAG 命中 {{ contexts.length }} 条
            </a-alert>
          </template>
          <a-table
            v-if="hasCaseRead"
            :data="cases"
            :columns="caseColumns"
            row-key="id"
            :pagination="tablePagination"
            style="margin-top: 12px"
          >
            <template #actions="{ record }">
              <a-space v-if="hasCaseWrite">
                <a-button size="mini" @click="openEditCase(record)">编辑</a-button>
                <a-popconfirm content="确认删除该用例？" @ok="removeCase(record.id)">
                  <a-button size="mini" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
              <span v-else>-</span>
            </template>
          </a-table>
        </a-tab-pane>
        <a-tab-pane key="org" title="计划与套件">
          <a-row :gutter="16">
            <a-col :span="12">
              <a-card title="测试计划" size="small" class="ai-panel">
                <a-form v-if="hasCaseWrite" layout="inline" style="margin-bottom: 8px">
                  <a-input v-model="planForm.name" placeholder="计划名称" style="width: 140px" />
                  <a-input v-model="planForm.description" placeholder="描述" style="width: 120px" />
                  <a-button type="primary" class="ai-action-btn" @click="createPlan">创建</a-button>
                </a-form>
                <a-list :data="testPlans">
                  <template #item="{ item }">
                    <a-list-item-meta :title="item.name" :description="`${item.status} · #${item.id}`" />
                  </template>
                </a-list>
              </a-card>
            </a-col>
            <a-col :span="12">
              <a-card title="测试套件" size="small" class="ai-panel">
                <a-form v-if="hasCaseWrite" layout="vertical" style="margin-bottom: 8px">
                  <a-input v-model="suiteForm.name" placeholder="套件名称" />
                  <a-input v-model="suiteForm.planId" placeholder="关联计划 ID（可选）" />
                  <a-button type="primary" class="ai-action-btn" @click="createSuite">创建套件</a-button>
                </a-form>
                <a-list :data="testSuites">
                  <template #item="{ item }">
                    <a-list-item>
                      <a-list-item-meta
                        :title="item.name"
                        :description="`用例 ${item.case_count} · 计划 ${item.plan_id ?? '-'}`"
                      />
                      <template v-if="hasCaseWrite" #actions>
                        <a-button size="mini" @click="openSuiteAssign(item.id)">分配用例</a-button>
                      </template>
                    </a-list-item>
                  </template>
                </a-list>
                <a-button v-if="hasCaseRead" size="small" style="margin-top: 8px" @click="loadTestOrg">刷新</a-button>
              </a-card>
            </a-col>
          </a-row>
        </a-tab-pane>
        <a-tab-pane key="openapi" title="OpenAPI 解析">
          <a-alert type="info" show-icon style="margin-bottom: 8px">
            粘贴完整 OpenAPI / Swagger（JSON 或 YAML，须含 paths），再点「解析并导入」。也可先点「填入示例」试跑。
          </a-alert>
          <a-textarea
            v-model="caseForm.openapiContent"
            placeholder='粘贴 OpenAPI JSON 或 YAML，例如：{ "openapi":"3.0.3", "paths": { "/health": { "get": { ... } } } }'
            :auto-size="{ minRows: 8 }"
            style="margin-top: 8px"
          />
          <a-space style="margin-top: 8px" wrap>
            <a-checkbox v-model="openapiPersist">解析后入库</a-checkbox>
            <a-button @click="fillSampleOpenApi">填入示例</a-button>
            <a-button
              v-if="hasCaseWrite"
              type="primary"
              class="ai-action-btn"
              :loading="openapiBusy"
              @click="importOpenApi"
            >
              解析并导入
            </a-button>
          </a-space>
          <div v-if="openapiPreview.length" style="margin-top: 12px">
            <div class="ai-section-title">本次解析结果（{{ openapiPreview.length }}）</div>
            <a-table
              size="small"
              row-key="id"
              :pagination="false"
              :data="openapiPreview"
              :columns="[
                { title: 'ID', dataIndex: 'id', width: 70 },
                { title: '标题', dataIndex: 'title', ellipsis: true },
                { title: '模块', dataIndex: 'module', width: 120 },
                { title: 'operationId', dataIndex: 'openapi_operation_id', ellipsis: true },
              ]"
            />
          </div>
        </a-tab-pane>
      </a-tabs>

      <a-modal v-model:visible="caseEditVisible" :title="editingCaseId ? '编辑用例' : '新建用例'" @ok="saveCaseEdit">
        <a-form layout="vertical">
          <a-form-item label="标题"><a-input v-model="caseEditForm.title" /></a-form-item>
          <a-form-item label="模块"><a-input v-model="caseEditForm.module" /></a-form-item>
          <a-form-item label="优先级">
            <a-select v-model="caseEditForm.priority">
              <a-option value="high">high</a-option>
              <a-option value="medium">medium</a-option>
              <a-option value="low">low</a-option>
            </a-select>
          </a-form-item>
          <a-form-item label="前置条件"><a-textarea v-model="caseEditForm.preconditions" :auto-size="{ minRows: 2 }" /></a-form-item>
          <a-form-item label="步骤（每行一步）"><a-textarea v-model="caseEditForm.stepsText" :auto-size="{ minRows: 4 }" /></a-form-item>
          <a-form-item label="预期结果"><a-textarea v-model="caseEditForm.expected" :auto-size="{ minRows: 2 }" /></a-form-item>
        </a-form>
      </a-modal>

      <a-modal v-model:visible="suiteAssignVisible" title="分配套件用例" @ok="saveSuiteAssign">
        <a-select v-model="suiteAssignCaseIds" multiple placeholder="选择用例" allow-search>
          <a-option v-for="c in cases" :key="c.id" :value="c.id">{{ c.id }} · {{ c.title }}</a-option>
        </a-select>
      </a-modal>
    </a-card>
  </div>
</template>

<style scoped>
.case-import-input {
  display: none;
}

.case-ai-panel {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(14, 165, 233, 0.22);
  background: linear-gradient(180deg, rgba(240, 249, 255, 0.9), rgba(255, 255, 255, 0.95));
}
</style>
