import { Message } from "@arco-design/web-vue";
import { computed, ref } from "vue";
import { authApi } from "../api/auth";
import { authStore } from "../api/auth-store";
import type { User, AuthSession } from "../types";

const authReady = ref(false);
const loading = ref(false);
const output = ref("");
const currentUser = ref<User | null>(null);

const isAuthenticated = computed(() => Boolean(currentUser.value));
const permissionCodes = computed(() => {
  const codes = new Set<string>();
  for (const role of currentUser.value?.roles || []) {
    for (const permission of role.permissions || []) {
      codes.add(permission.code);
    }
  }
  return codes;
});

const setOut = (value: unknown) => {
  output.value = JSON.stringify(value, null, 2);
};

const clearSessionState = () => {
  authStore.clear();
  currentUser.value = null;
};

const wrap = async (fn: () => Promise<void>, options?: { background?: boolean }) => {
  const background = options?.background ?? false;
  if (!background) {
    loading.value = true;
  }
  try {
    await fn();
  } catch (error) {
    const message = friendlyErrorMessage(error);
    // Navigation / intentional abort — do not toast as a failure.
    if (message === "请求已取消") {
      return;
    }
    const isAuthError =
      message.includes("authentication required") ||
      message.includes("invalid or expired token") ||
      message.includes("登录已失效") ||
      message.includes("认证");
    if (!background && isAuthError && authStore.getToken()) {
      clearSessionState();
    }
    if (!background) {
      setOut({ error: message });
      Message.error(message);
    }
  } finally {
    if (!background) {
      loading.value = false;
    }
  }
};

const friendlyErrorMessage = (error: unknown): string => {
  const raw = error instanceof Error ? error.message : String(error);
  if (!raw || raw === "undefined" || raw === "null") {
    return "操作失败，请稍后重试";
  }
  if (/is not a function/i.test(raw)) {
    return "当前功能暂不可用，请刷新页面后重试";
  }
  if (/Unexpected token|JSON\.parse|is not valid JSON/i.test(raw)) {
    return "脚本 JSON 格式无效，请检查后再保存";
  }
  if (/Failed to fetch|NetworkError|Load failed/i.test(raw)) {
    return "无法连接后端 API，请确认服务已启动";
  }
  if (/authentication required|invalid or expired token/i.test(raw)) {
    return "登录已失效，请重新登录";
  }
  return raw;
};

const runBackground = (fn: () => Promise<void>) => wrap(fn, { background: true });

const bootstrapSession = async () => {
  const token = authStore.getToken();
  if (!token) {
    currentUser.value = null;
    authReady.value = true;
    return;
  }
  try {
    currentUser.value = await authApi.me();
  } catch (error) {
    clearSessionState();
  } finally {
    authReady.value = true;
  }
};

const login = async (body: { username: string; password: string }) => {
  const session = await authApi.login(body);
  authStore.setToken(session.access_token);
  currentUser.value = session.user;
  output.value = "";
};

const logout = async () => {
  try {
    await authApi.logout();
  } catch {
    // Ignore transport errors and clear local session anyway.
  }
  clearSessionState();
  setOut({ logout: "ok" });
};

const refreshCurrentUser = async () => {
  currentUser.value = await authApi.me();
};

const applySession = (session: AuthSession) => {
  authStore.setToken(session.access_token);
  currentUser.value = session.user;
};

const hasPermission = (code: string) => permissionCodes.value.has(code);

const hasAnyPermission = (codes: string[]) => codes.some((code) => permissionCodes.value.has(code));

export function usePlatformStore() {
  return {
    authReady,
    loading,
    output,
    currentUser,
    isAuthenticated,
    permissionCodes,
    hasPermission,
    hasAnyPermission,
    setOut,
    wrap,
    runBackground,
    bootstrapSession,
    login,
    logout,
    refreshCurrentUser,
    applySession,
  };
}
