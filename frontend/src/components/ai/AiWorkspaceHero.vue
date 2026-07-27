<script setup lang="ts">
defineProps<{
  title: string;
  subtitle: string;
  badge?: string;
  statusLabel?: string;
  statusTone?: "online" | "offline" | "busy";
}>();
</script>

<template>
  <header class="ai-hero">
    <div class="ai-hero__main">
      <div class="ai-hero__orb" aria-hidden="true">
        <span class="ai-hero__ring" />
        <span class="ai-hero__core" />
      </div>
      <div class="ai-hero__text">
        <div class="ai-hero__meta">
          <span class="ai-hero__badge">{{ badge || "AI WORKSPACE" }}</span>
          <span
            v-if="statusLabel"
            class="ai-hero__status"
            :class="`ai-hero__status--${statusTone || 'online'}`"
          >
            <span class="ai-hero__pulse" />
            {{ statusLabel }}
          </span>
        </div>
        <h1 class="ai-hero__title">{{ title }}</h1>
        <p class="ai-hero__subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div v-if="$slots.extra" class="ai-hero__extra">
      <slot name="extra" />
    </div>
  </header>
</template>

<style scoped>
.ai-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 18px 20px;
  border: 1px solid rgba(14, 165, 233, 0.28);
  border-radius: 18px;
  background:
    radial-gradient(ellipse 80% 120% at 100% 0%, rgba(34, 211, 238, 0.12), transparent 45%),
    linear-gradient(135deg, rgba(14, 165, 233, 0.1), rgba(255, 255, 255, 0.94) 55%),
    #fff;
  box-shadow: 0 10px 28px rgba(14, 165, 233, 0.08);
  backdrop-filter: blur(8px);
}

.ai-hero__main {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-width: 0;
}

.ai-hero__orb {
  position: relative;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}

.ai-hero__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1.5px solid rgba(14, 165, 233, 0.45);
  animation: ai-orbit 4.5s linear infinite;
}

.ai-hero__core {
  position: absolute;
  inset: 10px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22d3ee, #0284c7);
  box-shadow: 0 0 16px rgba(14, 165, 233, 0.45);
}

.ai-hero__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.ai-hero__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0369a1;
  background: rgba(14, 165, 233, 0.12);
}

.ai-hero__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-2);
}

.ai-hero__status--online {
  color: #047857;
}

.ai-hero__status--offline {
  color: #b45309;
}

.ai-hero__status--busy {
  color: #0369a1;
}

.ai-hero__pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 0 currentColor;
  animation: ai-pulse 1.8s ease-out infinite;
}

.ai-hero__title {
  margin: 0;
  font-size: 22px;
  line-height: 1.25;
  font-weight: 700;
  color: var(--color-text-1);
}

.ai-hero__subtitle {
  margin: 6px 0 0;
  max-width: 720px;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  font-weight: 500;
}

.ai-hero__extra {
  display: flex;
  flex-direction: row;
  align-items: center;
  flex-shrink: 0;
  align-self: center;
  min-width: 0;
  padding-top: 0;
}

@keyframes ai-orbit {
  to {
    transform: rotate(360deg);
  }
}

@keyframes ai-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(4, 120, 87, 0.45);
  }
  70% {
    box-shadow: 0 0 0 8px rgba(4, 120, 87, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(4, 120, 87, 0);
  }
}

@media (max-width: 720px) {
  .ai-hero {
    flex-direction: column;
  }
}
</style>
