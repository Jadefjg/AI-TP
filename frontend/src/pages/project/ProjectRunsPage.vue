<script setup lang="ts">
import { createAsyncSection } from "./createAsyncSection";

const ProjectRunsSection = createAsyncSection(() => import("./sections/ProjectRunsSection.vue"));
</script>

<template>
  <ProjectRunsSection />
</template>
