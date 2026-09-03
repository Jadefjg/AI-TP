<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { authApi } from "../api/auth";
import AppBrandMark from "../components/AppBrandMark.vue";
import LoginBackground from "../components/LoginBackground.vue";
import { usePlatformStore } from "../state/platform";

const route = useRoute();
const router = useRouter();
const store = usePlatformStore();
const submitting = ref(false);
const registerForm = reactive({
  username: "",
  display_name: "",
  email: "",
  password: "",
  confirm_password: "",
});
const registerError = ref("");

onMounted(() => {
  store.output.value = "";
});

const submit = async () => {
  registerError.value = "";
  const username = registerForm.username.trim();
  if (username.length < 3) {
    registerError.value = "用户名至少 3 个字符";
    return;
  }
  if (registerForm.password.length < 8) {
    registerError.value = "密码至少 8 位";
    return;
  }
  if (registerForm.password !== registerForm.confirm_password) {
    registerError.value = "两次输入的密码不一致";
    return;
  }

  submitting.value = true;
  try {
    await authApi.register({
      username,
      password: registerForm.password,
      display_name: registerForm.display_name.trim() || null,
      email: registerForm.email.trim() || null,
    });
    const loginQuery: Record<string, string> = { username, registered: "1" };
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "";
    if (redirect) {
      loginQuery.redirect = redirect;
    }
    await router.replace({ path: "/login", query: loginQuery });
  } catch (error) {
    registerError.value = error instanceof Error ? error.message : String(error);
  } finally {
    submitting.value = false;
  }
};
</script>

<template>
  <div class="register-page">
    <LoginBackground />

    <div class="register-brand-float">
      <AppBrandMark />
    </div>

    <div class="register-shell">
      <div class="register-frame">
        <section class="register-card">
          <header class="register-card__header">
            <div class="register-card__badge">AI-TP · REGISTER</div>
            <h1 class="register-card__title">创建账号</h1>
            <p class="register-card__subtitle">注册后将加入默认租户，可使用平台测试与 AI 能力</p>
          </header>

          <a-form layout="vertical" class="register-form" @submit="submit">
            <a-form-item label="用户名" required>
              <a-input v-model="registerForm.username" placeholder="3–64 个字符" allow-clear size="large" />
            </a-form-item>
            <a-form-item label="显示名称">
              <a-input v-model="registerForm.display_name" placeholder="可选" allow-clear size="large" />
            </a-form-item>
            <a-form-item label="邮箱">
              <a-input v-model="registerForm.email" placeholder="可选" allow-clear size="large" />
            </a-form-item>
            <a-form-item label="密码" required>
              <a-input-password v-model="registerForm.password" placeholder="至少 8 位" size="large" />
            </a-form-item>
            <a-form-item label="确认密码" required>
              <a-input-password v-model="registerForm.confirm_password" placeholder="再次输入密码" size="large" />
            </a-form-item>
            <a-alert v-if="registerError" type="error" class="register-error" :title="registerError" show-icon />
            <a-button
              type="primary"
              html-type="submit"
              long
              size="large"
              :loading="submitting"
              class="register-submit"
            >
              {{ submitting ? "注册中…" : "注册" }}
            </a-button>
          </a-form>

          <p class="register-login">
            已有账号？
            <router-link to="/login" class="register-login__link">返回登录</router-link>
          </p>
        </section>
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

.register-page {
  position: relative;
  min-height: 100vh;
  padding: 24px;
  overflow-x: hidden;
  overflow-y: auto;
}

.register-brand-float {
  position: absolute;
  top: 24px;
  left: 24px;
  z-index: 2;
}

.register-shell {
  position: relative;
  z-index: 1;
  min-height: calc(100vh - 48px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.register-frame {
  width: min(440px, 100%);
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

.register-card {
  border-radius: 21px;
  padding: 36px 32px 28px;
  background: rgba(6, 11, 24, 0.82);
  backdrop-filter: blur(24px);
  color: #e2e8f0;
}

.register-card__badge {
  display: inline-flex;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.24em;
  color: #67e8f9;
  border: 1px solid rgba(56, 189, 248, 0.3);
  background: rgba(14, 165, 233, 0.06);
}

.register-card__title {
  margin: 14px 0 0;
  font-size: 24px;
  font-weight: 600;
  color: #f8fafc;
}

.register-card__subtitle {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(148, 163, 184, 0.88);
}

.register-form {
  margin-top: 24px;
}

.register-form :deep(.arco-form-item) {
  margin-bottom: 14px;
}

.register-form :deep(.arco-form-item-label) {
  margin-bottom: 6px;
  color: rgba(226, 232, 240, 0.85);
  font-size: 12px;
}

.register-form :deep(.arco-input-wrapper),
.register-form :deep(.arco-input-password) {
  background: rgba(8, 15, 30, 0.85);
  border-color: rgba(71, 85, 105, 0.5);
}

.register-form :deep(.arco-input),
.register-form :deep(.arco-input-password input) {
  color: #f1f5f9;
  background: transparent;
  -webkit-text-fill-color: #f1f5f9;
}

.register-error {
  margin-bottom: 14px;
}

.register-submit {
  margin-top: 6px;
  height: 46px;
  border: none;
  background: linear-gradient(135deg, #0891b2 0%, #4f46e5 50%, #7c3aed 100%);
}

.register-login {
  margin: 20px 0 0;
  padding-top: 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  font-size: 12px;
  text-align: center;
  color: rgba(148, 163, 184, 0.95);
}

.register-login__link {
  color: #67e8f9;
  text-decoration: none;
  margin-left: 4px;
}

.register-login__link:hover {
  text-decoration: underline;
}

@keyframes border-spin {
  to {
    --border-angle: 360deg;
  }
}

@media (prefers-reduced-motion: reduce) {
  .register-frame {
    animation: none;
  }
}
</style>
