<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  OPS_PIPELINE_STEPS,
  opsStepFromRoute,
  type OpsPipelineStep,
  type OpsPipelineStepKey,
} from "../../constants/opsPipeline";
import { usePlatformStore } from "../../state/platform";

const props = defineProps<{
  current?: OpsPipelineStepKey;
}>();

const store = usePlatformStore();
const route = useRoute();
const router = useRouter();

const canSee = (step: OpsPipelineStep) => {
  if (Array.isArray(step.permission)) {
    return store.hasAnyPermission(step.permission);
  }
  return store.hasPermission(step.permission);
};

const visibleSteps = computed(() => OPS_PIPELINE_STEPS.filter(canSee));

const activeKey = computed<OpsPipelineStepKey>(() => {
  const fromRoute = opsStepFromRoute(route);
  if (fromRoute && canSee(fromRoute)) return fromRoute.key;
  if (props.current) return props.current;
  return visibleSteps.value[0]?.key || "overview";
});

const currentIndex = computed(() =>
  visibleSteps.value.findIndex((step) => step.key === activeKey.value),
);

const go = (step: OpsPipelineStep) => {
  void router.push({ name: step.routeName });
};
</script>

<template>
  <nav class="ai-pipeline" aria-label="运维管理流水">
    <div class="ai-pipeline__row">
      <button
        v-for="(step, index) in visibleSteps"
        :key="step.key"
        type="button"
        class="ai-pipeline__step"
        :class="{
          'ai-pipeline__step--active': step.key === activeKey,
          'ai-pipeline__step--done': currentIndex > index,
        }"
        :aria-current="step.key === activeKey ? 'step' : undefined"
        @click="go(step)"
      >
        <span class="ai-pipeline__index">{{ step.short }}</span>
        <span class="ai-pipeline__copy">
          <span class="ai-pipeline__label">{{ step.label }}</span>
          <span
            class="ai-pipeline__hint"
            :class="{ 'ai-pipeline__hint--on': step.key === activeKey }"
          >
            {{ step.hint }}
          </span>
        </span>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.ai-pipeline {
  --pipeline-step-pad-y: 10px;
  --pipeline-step-pad-x: 12px;
  --pipeline-badge-size: 28px;
  --pipeline-border: rgba(15, 23, 42, 0.1);
  margin-bottom: 16px;
  padding: 12px 10px 10px;
  border: 1px solid rgba(14, 165, 233, 0.32);
  border-radius: 16px;
  background:
    radial-gradient(ellipse 50% 80% at 0% 0%, rgba(34, 211, 238, 0.1), transparent 55%),
    linear-gradient(180deg, rgba(240, 249, 255, 0.95), rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(8px);
  box-shadow:
    0 8px 24px rgba(14, 165, 233, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.85);
}

.ai-pipeline__row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: 8px;
  align-items: stretch;
}

.ai-pipeline__step {
  box-sizing: border-box;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  height: 100%;
  min-height: 48px;
  width: 100%;
  margin-top: 0;
  padding: var(--pipeline-step-pad-y) var(--pipeline-step-pad-x);
  border: 1px solid var(--pipeline-border);
  border-radius: 12px;
  background: rgba(14, 165, 233, 0.1);
  color: inherit;
  font: inherit;
  font-weight: 400;
  text-align: left;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.ai-pipeline__step:hover {
  background: rgba(14, 165, 233, 0.14);
}

.ai-pipeline__step--active {
  border-color: rgba(14, 165, 233, 0.45);
  background: rgba(14, 165, 233, 0.1);
}

.ai-pipeline__step--done .ai-pipeline__index {
  background: linear-gradient(135deg, #22d3ee, #0284c7);
  color: #fff;
}

.ai-pipeline__index {
  display: inline-grid;
  place-items: center;
  width: var(--pipeline-badge-size);
  height: var(--pipeline-badge-size);
  flex-shrink: 0;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #0369a1;
  background: rgba(240, 249, 255, 0.98);
  border: 1px solid rgba(14, 165, 233, 0.2);
}

.ai-pipeline__step--active .ai-pipeline__index {
  background: linear-gradient(135deg, #22d3ee, #0284c7);
  color: #fff;
  border-color: transparent;
}

.ai-pipeline__copy {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
  overflow: hidden;
}

.ai-pipeline__label {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--color-text-1);
  white-space: nowrap;
}

.ai-pipeline__hint {
  display: none;
  min-width: 0;
  font-size: 11px;
  line-height: 1.2;
  color: #0369a1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.ai-pipeline__hint--on {
  display: inline;
}

.ai-pipeline__hint--on::before {
  content: "·";
  margin-right: 6px;
  color: rgba(3, 105, 161, 0.55);
}

@media (max-width: 1280px) {
  .ai-pipeline__row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .ai-pipeline__row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .ai-pipeline__row {
    grid-template-columns: 1fr;
  }
}
</style>
