<script setup lang="ts">
import { useId } from "vue";

withDefaults(
  defineProps<{
    compact?: boolean;
  }>(),
  { compact: false },
);

const uid = useId().replace(/:/g, "");
const gradientId = `brand-g-${uid}`;
const coreId = `brand-core-${uid}`;
</script>

<template>
  <div class="app-brand-mark" :class="{ 'app-brand-mark--compact': compact }" aria-label="AI-TP">
    <svg class="app-brand-mark__icon" viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient :id="gradientId" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#22d3ee" />
          <stop offset="0.55" stop-color="#38bdf8" />
          <stop offset="1" stop-color="#6366f1" />
        </linearGradient>
        <radialGradient :id="coreId" cx="32" cy="32" r="14" gradientUnits="userSpaceOnUse">
          <stop stop-color="#e0f2fe" />
          <stop offset="0.45" stop-color="#22d3ee" />
          <stop offset="1" stop-color="#0369a1" />
        </radialGradient>
      </defs>
      <rect width="64" height="64" rx="14" fill="#06101f" />
      <path
        d="M32 8.5 52.5 20.5v23L32 55.5 11.5 43.5v-23L32 8.5Z"
        fill="none"
        :stroke="`url(#${gradientId})`"
        stroke-width="2.4"
        stroke-linejoin="round"
      />
      <circle cx="32" cy="32" r="9.5" :fill="`url(#${coreId})`" />
      <circle cx="32" cy="32" r="14.5" fill="none" stroke="#67e8f9" stroke-opacity="0.45" stroke-width="1.4" />
      <circle cx="32" cy="18.5" r="2.1" fill="#67e8f9" />
      <circle cx="44.2" cy="39" r="2.1" fill="#a5b4fc" />
      <circle cx="19.8" cy="39" r="2.1" fill="#38bdf8" />
      <path
        d="M32 20.6v8.2M41.5 37.4l-7.1-4.1M22.5 37.4l7.1-4.1"
        stroke="#e0f2fe"
        stroke-width="1.5"
        stroke-linecap="round"
      />
    </svg>
    <div v-if="!compact" class="app-brand-mark__text">
      <span class="app-brand-mark__name">AI-TP</span>
      <span class="app-brand-mark__tag">TEST PLATFORM</span>
    </div>
  </div>
</template>

<style scoped>
.app-brand-mark {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px 8px 8px;
  border-radius: 16px;
  background: rgba(6, 16, 31, 0.72);
  border: 1px solid rgba(56, 189, 248, 0.28);
  backdrop-filter: blur(14px);
  box-shadow:
    0 0 0 1px rgba(15, 23, 42, 0.35),
    0 12px 32px rgba(2, 8, 23, 0.35),
    0 0 24px rgba(34, 211, 238, 0.08);
}

.app-brand-mark--compact {
  padding: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.app-brand-mark__icon {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 12px;
  display: block;
}

.app-brand-mark--compact .app-brand-mark__icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
}

.app-brand-mark__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.app-brand-mark__name {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #f8fafc;
  line-height: 1.1;
}

.app-brand-mark__tag {
  font-size: 10px;
  letter-spacing: 0.18em;
  color: rgba(103, 232, 249, 0.85);
  line-height: 1.2;
}
</style>
