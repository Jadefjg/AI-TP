<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { AI_BUSY_MESSAGES } from "../../constants/aiPipeline";

const props = defineProps<{
  active: boolean;
  title?: string;
}>();

const message = ref(AI_BUSY_MESSAGES[0]);
let timer: number | undefined;
let index = 0;

const start = () => {
  stop();
  index = 0;
  message.value = AI_BUSY_MESSAGES[0];
  timer = window.setInterval(() => {
    index = (index + 1) % AI_BUSY_MESSAGES.length;
    message.value = AI_BUSY_MESSAGES[index];
  }, 1600);
};

const stop = () => {
  if (timer !== undefined) {
    window.clearInterval(timer);
    timer = undefined;
  }
};

watch(
  () => props.active,
  (active) => {
    if (active) start();
    else stop();
  },
);

onMounted(() => {
  if (props.active) start();
});

onBeforeUnmount(stop);
</script>

<template>
  <Transition name="ai-busy">
    <div v-if="active" class="ai-busy" role="status" aria-live="polite">
      <div class="ai-busy__card">
        <div class="ai-busy__visual" aria-hidden="true">
          <span class="ai-busy__ring ai-busy__ring--a" />
          <span class="ai-busy__ring ai-busy__ring--b" />
          <span class="ai-busy__dot" />
        </div>
        <div class="ai-busy__copy">
          <div class="ai-busy__meta">
            <span class="ai-busy__chip">NEURAL · BUSY</span>
          </div>
          <div class="ai-busy__title">{{ title || "AI 正在思考" }}</div>
          <div class="ai-busy__message">{{ message }}</div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.ai-busy {
  position: sticky;
  top: 8px;
  z-index: 20;
  margin-bottom: 14px;
}

.ai-busy__card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  border: 1px solid rgba(14, 165, 233, 0.35);
  border-radius: 14px;
  background:
    linear-gradient(120deg, rgba(14, 165, 233, 0.14), rgba(34, 211, 238, 0.08)),
    rgba(255, 255, 255, 0.82);
  box-shadow:
    0 10px 28px rgba(14, 165, 233, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
}

.ai-busy__visual {
  position: relative;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}

.ai-busy__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid transparent;
}

.ai-busy__ring--a {
  border-top-color: #22d3ee;
  border-right-color: #0ea5e9;
  animation: ai-spin 1.1s linear infinite;
}

.ai-busy__ring--b {
  inset: 5px;
  border-bottom-color: #38bdf8;
  border-left-color: #0284c7;
  animation: ai-spin 1.6s linear infinite reverse;
}

.ai-busy__dot {
  position: absolute;
  inset: 13px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22d3ee, #0284c7);
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.55);
}

.ai-busy__meta {
  margin-bottom: 2px;
}

.ai-busy__chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0369a1;
  background: rgba(14, 165, 233, 0.12);
  border: 1px solid rgba(14, 165, 233, 0.28);
}

.ai-busy__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-1);
}

.ai-busy__message {
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-text-2);
}

.ai-busy-enter-active,
.ai-busy-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.ai-busy-enter-from,
.ai-busy-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

@keyframes ai-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
