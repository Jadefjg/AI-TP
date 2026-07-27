import { computed, inject, provide, ref, type InjectionKey, type Ref } from "vue";
import { useRoute } from "vue-router";
import { projectsApi } from "../api/projects";
import { usePlatformStore } from "../state/platform";
import type { Project } from "../types";

export type ProjectScopeContext = {
  projectId: Ref<number>;
  project: Ref<Project | null>;
  reloadProject: () => Promise<void>;
};

export const projectScopeKey: InjectionKey<ProjectScopeContext> = Symbol("projectScope");

export function provideProjectScope() {
  const route = useRoute();
  const store = usePlatformStore();
  const project = ref<Project | null>(null);
  const projectId = computed(() => Number(route.params.id));

  const reloadProject = async () => {
    await store.wrap(async () => {
      project.value = await projectsApi.getProject(projectId.value);
    });
  };

  const ctx: ProjectScopeContext = { projectId, project, reloadProject };
  provide(projectScopeKey, ctx);
  return ctx;
}

export function useProjectScope() {
  const injected = inject(projectScopeKey, null);
  if (injected) {
    return injected;
  }
  const route = useRoute();
  const store = usePlatformStore();
  const project = ref<Project | null>(null);
  const projectId = computed(() => Number(route.params.id));
  const reloadProject = async () => {
    await store.wrap(async () => {
      project.value = await projectsApi.getProject(projectId.value);
    });
  };
  return { projectId, project, reloadProject };
}
