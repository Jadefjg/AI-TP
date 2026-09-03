<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import AiWorkspaceHero from "../../components/ai/AiWorkspaceHero.vue";
import OpsPipelineBar from "../../components/ops/OpsPipelineBar.vue";
import { OPS_PIPELINE_STEPS, opsStepFromRoute } from "../../constants/opsPipeline";
import { usePlatformStore } from "../../state/platform";

const store = usePlatformStore();
const route = useRoute();
const router = useRouter();

const canSee = (permission: string | string[]) => {
  if (Array.isArray(permission)) return store.hasAnyPermission(permission);
  return store.hasPermission(permission);
};

const visibleSteps = computed(() => OPS_PIPELINE_STEPS.filter((step) => canSee(step.permission)));

const currentStep = computed(
  () => opsStepFromRoute(route) || visibleSteps.value[0] || OPS_PIPELINE_STEPS[0],
);

const ensureVisibleChild = () => {
  const visible = visibleSteps.value;
  if (!visible.length) return;
  const current = opsStepFromRoute(route);
  const currentAllowed = current ? visible.some((item) => item.key === current.key) : false;
  if (!currentAllowed || route.name === "ops") {
    void router.replace({ name: visible[0].routeName });
  }
};

onMounted(() => ensureVisibleChild());
watch(
  () => [route.name, visibleSteps.value.map((item) => item.key).join(",")],
  () => ensureVisibleChild(),
);
</script>

<template>
  <div class="ops-page ai-workspace">
    <div class="ai-stage">
      <AiWorkspaceHero
        :title="currentStep.label"
        :subtitle="currentStep.subtitle"
        :badge="currentStep.badge"
        :status-label="currentStep.statusLabel"
        status-tone="online"
      />
      <OpsPipelineBar :current="currentStep.key" />
    </div>

    <RouterView />
  </div>
</template>
