<script setup lang="ts">
import { createAsyncSection } from "./createAsyncSection";

const ProjectCasesSection = createAsyncSection(() => import("./sections/ProjectCasesSection.vue"));
</script>

<template>
  <ProjectCasesSection />
</template>
