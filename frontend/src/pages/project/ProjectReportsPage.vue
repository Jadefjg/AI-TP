<script setup lang="ts">
import { createAsyncSection } from "./createAsyncSection";

const ProjectReportsSection = createAsyncSection(() => import("./sections/ProjectReportsSection.vue"));
</script>

<template>
  <ProjectReportsSection />
</template>
