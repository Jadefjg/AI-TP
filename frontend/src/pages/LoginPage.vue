<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import LoginBackground from "../components/LoginBackground.vue";
import { usePlatformStore } from "../state/platform";

const route = useRoute();
const router = useRouter();
const store = usePlatformStore();
const loginForm = reactive({ username: "admin", password: "admin123456" });
const loginError = ref("");

const features = [
  { icon: "◈", label: "AI 模块", desc: "五大智能引擎统一调度" },
  { icon: "⬡", label: "全链路", desc: "需求到报告闭环交付" },
  { icon: "◎", label: "多租户", desc: "权限审计与安全隔离" },
];

onMounted(() => {
  store.output.value = "";
  const username = typeof route.query.username === "string" ? route.query.username.trim() : "";
  if (username) {
    loginForm.username = username;
    loginForm.password = "";
  }
});

const submit = async () => {
  loginError.value = "";
  store.loading.value = true;
  try {
    await store.login(loginForm);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/dashboard";
    await router.replace(redirect);
  } catch (error) {
    loginError.value = error instanceof Error ? error.message : String(error);
  } finally {
    store.loading.value = false;
  }
};
</script>

<template>
  <div class="login-page">
    <LoginBackground />

    <div class="login-shell">
      <div class="login-frame">
        <div class="login-panel">
          <span class="corner corner--tl" />
          <span class="corner corner--tr" />
          <span class="corner corner--bl" />
          <span class="corner corner--br" />

          <section class="login-brand">
            <div class="login-brand__top">
              <div class="ai-core" aria-hidden="true">
                <span class="ai-core__ring ai-core__ring--1" />
                <span class="ai-core__ring ai-core__ring--2" />
                <span class="ai-core__ring ai-core__ring--3" />
                <span class="ai-core__orb" />
              </div>
              <div>
                <div class="login-brand__badge">
                  <span class="login-brand__pulse" />
                  AI · NEURAL · TEST
                </div>
                <h1 class="login-brand__title">智能测试中枢</h1>
              </div>
            </div>

            <p class="login-brand__desc">
              穿越需求迷雾，以 AI 洞察质量边界 —— 从评审、用例到执行与报告，全链路自主驱动。
            </p>

            <div class="login-brand__stats">
              <div class="stat">
                <span class="stat__value">5</span>
                <span class="stat__label">AI 模块</span>
              </div>
              <div class="stat">
                <span class="stat__value">∞</span>
                <span class="stat__label">测试维度</span>
              </div>
              <div class="stat">
                <span class="stat__value">0→1</span>
                <span class="stat__label">质量闭环</span>
              </div>
            </div>

            <div class="feature-grid">
              <div v-for="item in features" :key="item.label" class="feature-card">
                <span class="feature-card__icon">{{ item.icon }}</span>
                <div>
                  <div class="feature-card__label">{{ item.label }}</div>
                  <div class="feature-card__desc">{{ item.desc }}</div>
                </div>
              </div>
            </div>
          </section>

          <div class="login-divider" aria-hidden="true">
            <span class="login-divider__line" />
            <span class="login-divider__node" />
            <span class="login-divider__line" />
          </div>

          <section class="login-form">
            <div class="login-form__status">
              <span class="login-form__dot" />
              NEURAL LINK · STANDBY
            </div>

            <header class="login-form__header">
              <h2 class="login-form__title">进入控制台</h2>
              <p class="login-form__subtitle">验证身份以接入 AI 工作台与用户管理</p>
            </header>

            <a-form layout="vertical" class="login-form__body" @submit="submit">
              <a-form-item label="用户名" required>
                <a-input v-model="loginForm.username" placeholder="admin" allow-clear size="large" />
              </a-form-item>
              <a-form-item label="密码" required>
                <a-input-password v-model="loginForm.password" placeholder="密码" size="large" />
              </a-form-item>
              <a-alert v-if="loginError" type="error" class="login-error" :title="loginError" show-icon />
              <a-button
                type="primary"
                html-type="submit"
                long
                size="large"
                :loading="store.loading.value"
                class="login-submit"
              >
                <span class="login-submit__text">{{ store.loading.value ? "登录中…" : "登录" }}</span>
              </a-button>
            </a-form>

            <p class="login-footnote">
              默认账号 <code>admin / admin123456</code> · 生产环境请尽快修改密码
            </p>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@property --border-angle {
  syntax: "<angle>";
  initial-value: 0deg;
  inherits: false;
}

.login-page {
  position: relative;
  min-height: 100vh;
  max-height: 100vh;
  padding: 24px;
  overflow-x: hidden;
  overflow-y: auto;
}

.login-shell {
  position: relative;
  z-index: 1;
  min-height: calc(100vh - 48px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-frame {
  position: relative;
  width: min(980px, 100%);
  padding: 1px;
  border-radius: 22px;
  background: conic-gradient(
    from var(--border-angle),
    rgba(34, 211, 238, 0.15),
    rgba(56, 189, 248, 0.85),
    rgba(139, 92, 246, 0.85),
    rgba(99, 102, 241, 0.6),
    rgba(34, 211, 238, 0.15)
  );
  animation: border-spin 5s linear infinite;
  box-shadow:
    0 0 60px rgba(34, 211, 238, 0.12),
    0 0 120px rgba(139, 92, 246, 0.08);
}

.login-panel {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) auto minmax(300px, 380px);
  border-radius: 21px;
  overflow: hidden;
  background: rgba(6, 11, 24, 0.78);
  backdrop-filter: blur(24px);
  animation: panel-float 7s ease-in-out infinite;
}

.corner {
  position: absolute;
  width: 18px;
  height: 18px;
  border-color: rgba(56, 189, 248, 0.55);
  border-style: solid;
  z-index: 2;
  pointer-events: none;
}

.corner--tl {
  top: 14px;
  left: 14px;
  border-width: 2px 0 0 2px;
}

.corner--tr {
  top: 14px;
  right: 14px;
  border-width: 2px 2px 0 0;
}

.corner--bl {
  bottom: 14px;
  left: 14px;
  border-width: 0 0 2px 2px;
}

.corner--br {
  bottom: 14px;
  right: 14px;
  border-width: 0 2px 2px 0;
}

.login-brand {
  position: relative;
  padding: 40px 36px 36px;
  color: #e2e8f0;
}

.login-brand__top {
  display: flex;
  align-items: center;
  gap: 18px;
}

.ai-core {
  position: relative;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
}

.ai-core__orb {
  position: absolute;
  inset: 22px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #e0f2fe, #38bdf8 45%, #6366f1 100%);
  box-shadow:
    0 0 24px rgba(56, 189, 248, 0.8),
    0 0 48px rgba(99, 102, 241, 0.4);
  animation: core-pulse 3s ease-in-out infinite;
}

.ai-core__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(56, 189, 248, 0.35);
}

.ai-core__ring--1 {
  animation: ring-pulse 3s ease-in-out infinite;
}

.ai-core__ring--2 {
  inset: -6px;
  border-color: rgba(139, 92, 246, 0.25);
  animation: ring-pulse 3s ease-in-out infinite 0.6s;
}

.ai-core__ring--3 {
  inset: -12px;
  border-color: rgba(56, 189, 248, 0.15);
  animation: ring-pulse 3s ease-in-out infinite 1.2s;
}

.login-brand__badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.24em;
  color: #67e8f9;
  border: 1px solid rgba(56, 189, 248, 0.3);
  background: rgba(14, 165, 233, 0.06);
}

.login-brand__pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22d3ee;
  box-shadow: 0 0 10px #22d3ee;
  animation: dot-blink 2s ease-in-out infinite;
}

.login-brand__title {
  margin: 10px 0 0;
  font-size: clamp(1.6rem, 2.8vw, 2.15rem);
  line-height: 1.15;
  font-weight: 700;
  background: linear-gradient(120deg, #f8fafc 0%, #7dd3fc 35%, #c4b5fd 65%, #f8fafc 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: title-shimmer 6s linear infinite;
}

.login-brand__desc {
  margin: 18px 0 0;
  font-size: 13px;
  line-height: 1.75;
  color: rgba(203, 213, 225, 0.72);
  max-width: 420px;
}

.login-brand__stats {
  display: flex;
  gap: 20px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat__value {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #22d3ee, #a78bfa);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.stat__label {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.85);
  letter-spacing: 0.06em;
}

.feature-grid {
  display: grid;
  gap: 10px;
  margin-top: 20px;
}

.feature-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(56, 189, 248, 0.12);
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.06), rgba(139, 92, 246, 0.04));
  transition: border-color 0.25s, box-shadow 0.25s, transform 0.25s;
}

.feature-card:hover {
  border-color: rgba(56, 189, 248, 0.35);
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.08);
  transform: translateX(4px);
}

.feature-card__icon {
  font-size: 18px;
  color: #67e8f9;
  text-shadow: 0 0 12px rgba(34, 211, 238, 0.6);
  line-height: 1;
  margin-top: 2px;
}

.feature-card__label {
  font-size: 13px;
  font-weight: 600;
  color: #f1f5f9;
}

.feature-card__desc {
  margin-top: 2px;
  font-size: 11px;
  color: rgba(148, 163, 184, 0.9);
}

.login-divider {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 4px;
  background: rgba(2, 6, 23, 0.35);
}

.login-divider__line {
  flex: 1;
  width: 1px;
  background: linear-gradient(to bottom, transparent, rgba(56, 189, 248, 0.4), transparent);
}

.login-divider__node {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22d3ee;
  box-shadow: 0 0 14px rgba(34, 211, 238, 0.9);
  animation: dot-blink 2.5s ease-in-out infinite;
}

.login-form {
  display: flex;
  flex-direction: column;
  padding: 36px 32px 28px;
  background: linear-gradient(180deg, rgba(2, 6, 23, 0.5) 0%, rgba(15, 23, 42, 0.25) 100%);
}

.login-form__status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  margin-bottom: 20px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 10px;
  letter-spacing: 0.18em;
  color: rgba(103, 232, 249, 0.85);
  background: rgba(14, 165, 233, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.15);
}

.login-form__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 8px #34d399;
  animation: dot-blink 1.8s ease-in-out infinite;
}

.login-form__header {
  margin-bottom: 22px;
}

.login-form__title {
  margin: 0;
  font-size: 21px;
  font-weight: 600;
  color: #f8fafc;
  letter-spacing: 0.04em;
}

.login-form__subtitle {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(148, 163, 184, 0.88);
}

.login-form__body :deep(.arco-form-item) {
  margin-bottom: 16px;
}

.login-form__body :deep(.arco-form-item-label) {
  margin-bottom: 6px;
  color: rgba(226, 232, 240, 0.85);
  font-size: 12px;
  letter-spacing: 0.04em;
}

.login-form__body :deep(.arco-input-wrapper),
.login-form__body :deep(.arco-input-password) {
  background: rgba(8, 15, 30, 0.85);
  border-color: rgba(71, 85, 105, 0.5);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.login-form__body :deep(.arco-input-wrapper:focus-within),
.login-form__body :deep(.arco-input-password:focus-within) {
  border-color: rgba(56, 189, 248, 0.7);
  box-shadow:
    0 0 0 2px rgba(56, 189, 248, 0.12),
    0 0 20px rgba(34, 211, 238, 0.1);
}

.login-form__body :deep(.arco-input),
.login-form__body :deep(.arco-input-password input) {
  color: #f1f5f9;
  background: transparent;
  -webkit-text-fill-color: #f1f5f9;
}

.login-form__body :deep(.arco-input::placeholder),
.login-form__body :deep(.arco-input-password input::placeholder) {
  color: rgba(148, 163, 184, 0.75);
}

.login-form__body :deep(.arco-input:-webkit-autofill),
.login-form__body :deep(.arco-input-password input:-webkit-autofill) {
  -webkit-text-fill-color: #f1f5f9;
  caret-color: #f1f5f9;
  box-shadow: 0 0 0 1000px rgba(8, 15, 30, 0.85) inset;
}

.login-error {
  margin-bottom: 14px;
}

.login-submit {
  position: relative;
  margin-top: 6px;
  height: 46px;
  overflow: hidden;
  border: none;
  background: linear-gradient(135deg, #0891b2 0%, #4f46e5 50%, #7c3aed 100%);
  box-shadow:
    0 8px 32px rgba(59, 130, 246, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
  transition: transform 0.2s, box-shadow 0.2s;
}

.login-submit::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    105deg,
    transparent 35%,
    rgba(255, 255, 255, 0.22) 50%,
    transparent 65%
  );
  transform: translateX(-120%);
  animation: btn-shimmer 3.5s ease-in-out infinite;
}

.login-submit:hover {
  transform: translateY(-1px);
  box-shadow:
    0 12px 40px rgba(99, 102, 241, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.login-submit__text {
  position: relative;
  letter-spacing: 0.28em;
  font-size: 13px;
}

.login-footnote {
  margin: 20px 0 0;
  padding-top: 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  font-size: 11px;
  line-height: 1.65;
  color: rgba(100, 116, 139, 0.95);
  text-align: center;
}

.login-footnote code {
  color: #67e8f9;
  background: rgba(14, 165, 233, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

@keyframes border-spin {
  to {
    --border-angle: 360deg;
  }
}

@keyframes panel-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-6px);
  }
}

@keyframes title-shimmer {
  to {
    background-position: 200% center;
  }
}

@keyframes core-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.08);
    opacity: 0.92;
  }
}

@keyframes ring-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.6;
  }
  50% {
    transform: scale(1.06);
    opacity: 1;
  }
}

@keyframes dot-blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

@keyframes btn-shimmer {
  0%,
  70%,
  100% {
    transform: translateX(-120%);
  }
  85% {
    transform: translateX(120%);
  }
}

@media (max-width: 860px) {
  .login-panel {
    grid-template-columns: 1fr;
  }

  .login-divider {
    flex-direction: row;
    padding: 0 24px;
    height: auto;
  }

  .login-divider__line {
    flex: 1;
    height: 1px;
    width: auto;
    background: linear-gradient(to right, transparent, rgba(56, 189, 248, 0.4), transparent);
  }

  .login-brand {
    padding: 28px 24px 20px;
    text-align: center;
  }

  .login-brand__top {
    flex-direction: column;
  }

  .login-brand__desc {
    margin-inline: auto;
  }

  .login-brand__stats {
    justify-content: center;
  }

  .feature-grid {
    max-width: 360px;
    margin-inline: auto;
  }

  .login-form {
    padding: 24px 24px 22px;
  }

  .login-form__status {
    align-self: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-frame,
  .login-panel,
  .login-brand__title,
  .ai-core__orb,
  .ai-core__ring,
  .login-submit::before,
  .login-form__dot,
  .login-divider__node,
  .login-brand__pulse {
    animation: none;
  }

  .feature-card:hover {
    transform: none;
  }
}
</style>
