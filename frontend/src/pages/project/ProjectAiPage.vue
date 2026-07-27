<script setup lang="ts">
import { createAsyncSection } from "./createAsyncSection";

const ProjectAiSection = createAsyncSection(() => import("./sections/ProjectAiSection.vue"));
</script>

<template>
  <ProjectAiSection />
</template>
