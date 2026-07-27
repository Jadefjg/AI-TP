import { defineAsyncComponent, type Component } from "vue";
import ProjectSectionLoading from "./ProjectSectionLoading.vue";

type SectionModule = { default: Component };

export function createAsyncSection(loader: () => Promise<SectionModule>) {
  return defineAsyncComponent({
    loader,
    delay: 120,
    timeout: 60_000,
    loadingComponent: ProjectSectionLoading,
  });
}
