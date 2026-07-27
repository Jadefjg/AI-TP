<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { IconMore } from "@arco-design/web-vue/es/icon";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { projectsApi } from "../api/projects";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { buildPipelineQuery, rememberPipelineProjectId } from "../constants/aiPipeline";
import { LIST_PAGE_SIZE_OPTIONS } from "../constants/listPagination";
import { usePlatformStore } from "../state/platform";
import type { Project } from "../types";

const store = usePlatformStore();
const router = useRouter();
const projects = ref<Project[]>([]);
const listPagination = reactive({
  current: 1,
  pageSize: 10,
});
const createOpen = ref(false);
const editingId = ref<number | null>(null);
const projectForm = reactive({
  name: "",
  description: "",
  code_root: "",
  repo_source: "local" as "local" | "remote" | "deployed",
  repo_branch: "main",
});

const canWrite = computed(() => store.hasPermission("project.write"));
const isEditing = computed(() => editingId.value != null);
const formModalTitle = computed(() => (isEditing.value ? "编辑项目" : "创建项目"));
const formSubmitLabel = computed(() => (isEditing.value ? "保存修改" : "创建项目"));
const nameKeyword = ref("");

const filteredProjects = computed(() => {
  const q = nameKeyword.value.trim().toLowerCase();
  if (!q) return projects.value;
  return projects.value.filter((item) => item.name.toLowerCase().includes(q));
});

const paginatedProjects = computed(() => {
  const start = (listPagination.current - 1) * listPagination.pageSize;
  return filteredProjects.value.slice(start, start + listPagination.pageSize);
});

const locationPlaceholder = computed(() => {
  if (projectForm.repo_source === "remote") {
    return "https://github.com/org/repo.git 或 git@github.com:org/repo.git";
  }
  if (projectForm.repo_source === "deployed") {
    return "https://app.example.com 或 http://127.0.0.1:8002";
  }
  return "/Users/you/Documents/Work/my-project";
});

const locationLabel = computed(() => {
  if (projectForm.repo_source === "remote") return "Git 仓库 URL";
  if (projectForm.repo_source === "deployed") return "部署访问地址";
  return "本地绝对路径";
});

const locationHint = computed(() => {
  if (projectForm.repo_source === "remote") {
    return "填写可访问的 Git 仓库 URL，平台会在首次测试时自动 clone / pull";
  }
  if (projectForm.repo_source === "deployed") {
    return "项目已上线时使用：填写可访问的服务/站点 URL，用于接口、性能、安全等在线测试";
  }
  return "填写本机代码仓库的绝对路径（需后端可读取到该目录）";
});

watch(nameKeyword, () => {
  listPagination.current = 1;
});

watch(
  () => filteredProjects.value.length,
  (total) => {
    const maxPage = Math.max(1, Math.ceil(total / listPagination.pageSize) || 1);
    if (listPagination.current > maxPage) {
      listPagination.current = maxPage;
    }
  },
);

const isGitRemoteLocation = (value: string) => {
  const text = value.trim();
  if (/^(git@|ssh:\/\/)/i.test(text)) return true;
  if (!/^https?:\/\//i.test(text)) return false;
  const lowered = text.toLowerCase();
  if (lowered.endsWith(".git") || lowered.includes("/.git/") || lowered.includes("/git/")) return true;
  return /(github\.com|gitlab\.com|gitee\.com|bitbucket\.org|gitcode\.com)/i.test(text);
};

const isDeployedLocation = (value: string) =>
  /^https?:\/\//i.test(value.trim()) && !isGitRemoteLocation(value);

const suggestNameFromLocation = (location: string) => {
  const raw = location.trim().replace(/\/+$/, "").replace(/\.git$/i, "");
  if (!raw) return "";
  try {
    if (/^https?:\/\//i.test(raw)) {
      const host = new URL(raw).hostname.replace(/^www\./, "");
      return host.slice(0, 80);
    }
  } catch {
    /* ignore */
  }
  const parts = raw.split(/[/\\:]/);
  const leaf = parts.filter(Boolean).pop() || "";
  return leaf.slice(0, 80);
};

const onLocationBlur = () => {
  const location = projectForm.code_root.trim();
  if (!location) return;
  if (isGitRemoteLocation(location)) {
    projectForm.repo_source = "remote";
  } else if (isDeployedLocation(location)) {
    projectForm.repo_source = "deployed";
  }
  if (!projectForm.name.trim()) {
    const suggested = suggestNameFromLocation(location);
    if (suggested) projectForm.name = suggested;
  }
};

const onSourceChange = (value: string | number | boolean) => {
  const raw = String(value);
  const source = raw === "remote" || raw === "deployed" ? raw : "local";
  projectForm.repo_source = source;
  const location = projectForm.code_root.trim();
  if (!location) return;
  if (source === "remote" && !isGitRemoteLocation(location)) projectForm.code_root = "";
  if (source === "deployed" && !isDeployedLocation(location)) projectForm.code_root = "";
  if (source === "local" && (isGitRemoteLocation(location) || isDeployedLocation(location))) {
    projectForm.code_root = "";
  }
};

const resetSearch = () => {
  nameKeyword.value = "";
};

const sourceLabel = (value: string) => {
  if (value === "remote") return "远程仓库";
  if (value === "deployed") return "已部署";
  if (value === "local") return "本地仓库";
  return value;
};

const sourceTagColor = (value: string) => {
  if (value === "remote") return "arcoblue";
  if (value === "deployed") return "orangered";
  return "green";
};

const resetProjectForm = () => {
  projectForm.name = "";
  projectForm.description = "";
  projectForm.code_root = "";
  projectForm.repo_source = "local";
  projectForm.repo_branch = "main";
  editingId.value = null;
};

const openCreateModal = () => {
  resetProjectForm();
  createOpen.value = true;
};

const openEditModal = (item: Project) => {
  editingId.value = item.id;
  projectForm.name = item.name;
  projectForm.description = item.description || "";
  projectForm.code_root = item.code_root;
  projectForm.repo_source =
    item.repo_source === "remote" || item.repo_source === "deployed" ? item.repo_source : "local";
  projectForm.repo_branch = item.repo_branch || "main";
  createOpen.value = true;
};

const closeCreateModal = () => {
  createOpen.value = false;
  editingId.value = null;
};

const loadProjects = () =>
  store.wrap(async () => {
    projects.value = await projectsApi.listProjects();
    store.setOut(projects.value);
  });

const validateProjectForm = () => {
  const name = projectForm.name.trim();
  const codeRoot = projectForm.code_root.trim();
  const branch = projectForm.repo_branch.trim() || "main";
  const source = projectForm.repo_source;

  if (!name) {
    Message.warning("请输入项目名");
    return null;
  }
  if (!codeRoot) {
    if (source === "remote") Message.warning("请输入远程仓库 URL");
    else if (source === "deployed") Message.warning("请输入已部署项目的访问 URL");
    else Message.warning("请输入本地绝对路径");
    return null;
  }
  if (source === "remote" && !isGitRemoteLocation(codeRoot)) {
    Message.warning("远程仓库请使用 git@ / ssh://，或 Git 托管地址 / .git 结尾的 http(s) URL");
    return null;
  }
  if (source === "deployed" && !isDeployedLocation(codeRoot)) {
    Message.warning("已部署项目请填写 http(s) 运行地址（不要填 Git 仓库地址）");
    return null;
  }
  if (source === "local" && (isGitRemoteLocation(codeRoot) || isDeployedLocation(codeRoot))) {
    Message.warning("当前选择的是本地仓库，请填写本机绝对路径");
    return null;
  }
  if (source === "local" && !codeRoot.startsWith("/") && !/^[A-Za-z]:[\\/]/.test(codeRoot)) {
    Message.warning("本地仓库请填写绝对路径，例如 /Users/you/work/app");
    return null;
  }
  return {
    name,
    description: projectForm.description.trim() || null,
    code_root: codeRoot,
    repo_source: source,
    repo_branch: source === "deployed" ? null : branch,
  };
};

const submitProjectForm = () => {
  const payload = validateProjectForm();
  if (!payload) return;

  void store.wrap(async () => {
    if (editingId.value != null) {
      const result = await projectsApi.updateProject(editingId.value, payload);
      store.setOut(result);
      closeCreateModal();
      resetProjectForm();
      await loadProjects();
      Message.success(`项目「${payload.name}」已更新`);
      return;
    }

    const result = await projectsApi.createProject(payload);
    store.setOut(result);
    closeCreateModal();
    resetProjectForm();
    await loadProjects();
    const tips =
      payload.repo_source === "remote"
        ? `远程项目「${payload.name}」已创建，首次执行测试时会自动同步仓库`
        : payload.repo_source === "deployed"
          ? `已部署项目「${payload.name}」已创建，可用于接口 / 性能 / 安全在线测试`
          : `本地项目「${payload.name}」已创建`;
    Message.success(tips);
    if (result?.id) {
      rememberPipelineProjectId(result.id);
    }
  });
};

const openProject = (id: number) => {
  rememberPipelineProjectId(id);
  router.push({ name: "project-cases", params: { id } });
};

const enterPipeline = (id: number) => {
  rememberPipelineProjectId(id);
  void router.push({
    name: "requirements",
    query: buildPipelineQuery({ projectId: id }),
  });
};

const removeProject = (item: Project) => {
  void store.wrap(async () => {
    await projectsApi.deleteProject(item.id);
    await loadProjects();
    Message.success(`项目「${item.name}」已删除`);
  });
};

const onProjectAction = (
  key: string | number | Record<string, unknown> | undefined,
  item: Project,
) => {
  if (typeof key !== "string") return;
  if (key === "pipeline") {
    enterPipeline(item.id);
    return;
  }
  if (key === "detail") {
    openProject(item.id);
    return;
  }
  if (key === "edit") {
    openEditModal(item);
    return;
  }
  if (key === "delete") {
    Modal.confirm({
      title: "删除项目",
      content: `确定删除项目「${item.name}」？此操作不可恢复。`,
      okText: "删除",
      cancelText: "取消",
      okButtonProps: { status: "danger" },
      onOk: () => removeProject(item),
    });
  }
};

onMounted(() => {
  void loadProjects();
});
</script>

<template>
  <div class="projects-page ai-workspace ai-page-fill">
    <AiWorkspaceHero
      title="项目管理"
      subtitle="绑定本地仓库、远程 Git 或已部署 URL，作为智能流水的统一项目上下文"
      badge="AI · PROJECTS"
      :status-label="store.loading.value ? '同步中' : '就绪'"
      :status-tone="store.loading.value ? 'busy' : 'online'"
    >
      <template #extra>
        <a-space>
          <a-button :loading="store.loading.value" @click="loadProjects">刷新</a-button>
          <a-button v-if="canWrite" type="primary" class="ai-action-btn" @click="openCreateModal">
            新建项目
          </a-button>
        </a-space>
      </template>
    </AiWorkspaceHero>

    <a-card class="projects-toolbar ai-panel" :bordered="false">
      <div class="projects-toolbar__inner">
        <div class="projects-toolbar__left">
          <span class="projects-toolbar__label">项目名称</span>
          <a-input
            v-model="nameKeyword"
            class="projects-toolbar__input"
            placeholder="请输入项目名称"
            allow-clear
            size="medium"
            @press-enter="listPagination.current = 1"
          />
          <a-button size="medium" @click="listPagination.current = 1">查询</a-button>
          <a-button size="medium" @click="resetSearch">重置</a-button>
        </div>
        <div class="projects-toolbar__right">
          <span class="projects-toolbar__count">共 {{ filteredProjects.length }} 条</span>
        </div>
      </div>
    </a-card>

    <a-modal
      v-model:visible="createOpen"
      :title="formModalTitle"
      :width="780"
      :mask-closable="false"
      unmount-on-close
      @cancel="closeCreateModal"
    >
      <div class="create-modes">
        <button
          type="button"
          class="create-mode"
          :class="{ 'create-mode--active': projectForm.repo_source === 'local' }"
          @click="onSourceChange('local')"
        >
          <div class="create-mode__title">本地代码仓库</div>
          <div class="create-mode__desc">绑定本机已有 Git/工程目录的绝对路径</div>
        </button>
        <button
          type="button"
          class="create-mode"
          :class="{ 'create-mode--active': projectForm.repo_source === 'remote' }"
          @click="onSourceChange('remote')"
        >
          <div class="create-mode__title">远程仓库 URL</div>
          <div class="create-mode__desc">添加 GitHub / GitLab / 私有仓库地址并自动同步</div>
        </button>
        <button
          type="button"
          class="create-mode"
          :class="{ 'create-mode--active': projectForm.repo_source === 'deployed' }"
          @click="onSourceChange('deployed')"
        >
          <div class="create-mode__title">已部署 URL</div>
          <div class="create-mode__desc">项目已上线时，填写可访问的服务/站点地址</div>
        </button>
      </div>

      <a-form :model="projectForm" layout="vertical" class="create-form">
        <a-row :gutter="16">
          <a-col :xs="24" :md="projectForm.repo_source === 'deployed' ? 24 : 12">
            <a-form-item label="项目名称" required>
              <a-input v-model="projectForm.name" placeholder="例如：UGC 社区" allow-clear />
            </a-form-item>
          </a-col>
          <a-col v-if="projectForm.repo_source !== 'deployed'" :xs="24" :md="12">
            <a-form-item label="默认分支">
              <a-input v-model="projectForm.repo_branch" placeholder="main" allow-clear />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item :label="locationLabel" required>
          <a-input
            v-model="projectForm.code_root"
            :placeholder="locationPlaceholder"
            allow-clear
            @blur="onLocationBlur"
          />
          <div class="create-form__hint">{{ locationHint }}</div>
        </a-form-item>
        <a-form-item label="项目描述（可选）">
          <a-textarea
            v-model="projectForm.description"
            :auto-size="{ minRows: 2, maxRows: 4 }"
            placeholder="补充业务背景，便于后续 AI 测试识别项目上下文"
          />
        </a-form-item>
      </a-form>

      <template #footer>
        <a-space>
          <a-button v-if="!isEditing" @click="resetProjectForm">清空</a-button>
          <a-button @click="closeCreateModal">取消</a-button>
          <a-button type="primary" :loading="store.loading.value" @click="submitProjectForm">
            {{ formSubmitLabel }}
          </a-button>
        </a-space>
      </template>
    </a-modal>

    <a-card title="项目列表" class="projects-card ai-panel ai-fill-panel">
      <div class="project-table-wrap">
        <table class="project-table">
          <colgroup>
            <col class="col-id" />
            <col class="col-name" />
            <col class="col-source" />
            <col class="col-path" />
            <col class="col-branch" />
            <col class="col-action" />
          </colgroup>
          <thead>
            <tr>
              <th>ID</th>
              <th>项目</th>
              <th>来源</th>
              <th>路径 / URL</th>
              <th>分支</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!projects.length">
              <td colspan="6" class="cell-empty">暂无项目，请先使用上方「新建项目」创建</td>
            </tr>
            <tr v-else-if="!filteredProjects.length">
              <td colspan="6" class="cell-empty">无匹配项目，请调整搜索条件</td>
            </tr>
            <tr v-for="item in paginatedProjects" :key="item.id" class="project-table__data">
              <td class="cell-id">{{ item.id }}</td>
              <td>{{ item.name }}</td>
              <td>
                <a-tag :color="sourceTagColor(item.repo_source)" size="small">
                  {{ sourceLabel(item.repo_source) }}
                </a-tag>
              </td>
              <td class="cell-path" :title="item.code_root">{{ item.code_root }}</td>
              <td>{{ item.repo_branch || "—" }}</td>
              <td class="cell-action">
                <a-dropdown
                  trigger="click"
                  position="br"
                  :popup-max-height="false"
                  @select="(key) => onProjectAction(key, item)"
                >
                  <a-button type="text" size="small" class="project-more-btn" aria-label="更多操作">
                    <icon-more />
                  </a-button>
                  <template #content>
                    <a-doption value="pipeline">智能流水</a-doption>
                    <a-doption value="detail">详情</a-doption>
                    <a-doption v-if="canWrite" value="edit">编辑</a-doption>
                    <a-doption v-if="canWrite" value="delete" class="project-action-danger">
                      删除
                    </a-doption>
                  </template>
                </a-dropdown>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <a-pagination
        v-if="filteredProjects.length"
        v-model:current="listPagination.current"
        v-model:page-size="listPagination.pageSize"
        class="list-pagination"
        :total="filteredProjects.length"
        :show-total="true"
        :show-page-size="true"
        :show-jumper="true"
        :page-size-options="LIST_PAGE_SIZE_OPTIONS"
        :page-size-props="{ style: { width: '116px' } }"
      />
    </a-card>
  </div>
</template>

<style scoped>
.projects-toolbar {
  margin-bottom: 16px;
}

.projects-toolbar :deep(.arco-card-body) {
  padding: 12px 16px;
}

.projects-toolbar__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.projects-toolbar__left,
.projects-toolbar__right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.projects-toolbar__label {
  color: var(--color-text-2);
  font-size: 14px;
  white-space: nowrap;
}

.projects-toolbar__input {
  width: 220px;
}

.projects-toolbar__count {
  color: var(--color-text-3);
  font-size: 14px;
  white-space: nowrap;
}

.create-modes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.create-mode {
  text-align: left;
  padding: 14px 16px;
  border: 1px solid var(--color-border-2);
  border-radius: 12px;
  background: rgba(14, 165, 233, 0.1);
  color: inherit;
  font: inherit;
  font-weight: 400;
  width: 100%;
  margin-top: 0;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease, background 0.15s ease;
}

.create-mode:hover {
  border-color: rgba(14, 165, 233, 0.45);
  background: rgba(14, 165, 233, 0.14);
  transform: translateY(-1px);
}

.create-mode--active {
  border-color: rgba(14, 165, 233, 0.55);
  background: rgba(14, 165, 233, 0.1);
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.08);
}

.create-mode__title {
  font-size: 14px;
  font-weight: 650;
  color: var(--color-text-1);
}

.create-mode__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-3);
}

.create-form__hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-3);
  line-height: 1.5;
}

.projects-card :deep(.arco-card-body) {
  padding-top: 8px;
}

.project-table-wrap {
  overflow-x: auto;
}

.project-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  border: 1px solid var(--color-border-2);
  border-radius: 4px;
  overflow: hidden;
  font-size: 14px;
}

.project-table .col-id {
  width: 72px;
}

.project-table .col-name {
  width: 140px;
}

.project-table .col-source {
  width: 120px;
}

.project-table .col-branch {
  width: 112px;
}

.project-table .col-action {
  width: 72px;
}

.project-table th,
.project-table td {
  height: 44px;
  padding: 6px 12px;
  border: 1px solid var(--color-border-2);
  vertical-align: middle;
  box-sizing: border-box;
}

.project-table th {
  background: var(--color-fill-1);
  color: var(--color-text-1);
  font-weight: 600;
  text-align: left;
}

.project-table__data:hover td {
  background: var(--color-fill-2);
}

.cell-id {
  text-align: center;
  color: var(--color-text-2);
}

.cell-action {
  text-align: center;
  white-space: nowrap;
}

.project-more-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  padding: 0 6px;
  font-size: 16px;
}

.project-action-danger {
  color: rgb(var(--red-6)) !important;
}

.cell-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-empty {
  text-align: center;
  color: var(--color-text-3);
  height: 56px !important;
}

@media (max-width: 900px) {
  .create-modes {
    grid-template-columns: 1fr;
  }
}
</style>
