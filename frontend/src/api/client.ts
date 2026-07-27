import { authStore } from "./auth-store";
import { BASE_URL } from "./config";

async function parseResponseJson(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text();
  if (!text) {
    if (res.status >= 500) {
      throw new Error("后端服务不可用，请确认 API 已启动（默认 http://127.0.0.1:8002）");
    }
    return {};
  }
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    throw new Error(res.ok ? "响应解析失败" : `请求失败 (${res.status})`);
  }
}

function formatApiError(data: Record<string, unknown>, status: number): string {
  const detail = data.detail;
  if (typeof detail === "string" && detail) {
    const known: Record<string, string> = {
      "Internal Server Error": "服务内部错误，请稍后重试",
      "Not Found": "资源不存在",
      "Unauthorized": "登录已失效，请重新登录",
      "Forbidden": "当前账号无权限执行该操作",
      "organization slug already exists": "部门编码已存在，请更换编码",
      "部门编码已存在，请更换编码": "部门编码已存在，请更换编码",
      "run not found": "找不到该 Run，请确认 Run ID 是否正确",
      "run 仍在执行中，请稍后重试": "Run 仍在执行中，请完成后再生成报告",
    };
    return known[detail] || detail;
  }
  if (Array.isArray(detail)) {
    const fieldLabels: Record<string, string> = {
      requirement_text: "需求内容",
      openapi_content: "OpenAPI 文档",
      original_text: "AI 原始输出",
      corrected_text: "人工修正内容",
      module_type: "模块类型",
      source_type: "来源类型",
      project_id: "项目",
      password: "密码",
      username: "用户名",
    };
    const translateMsg = (msg: string) => {
      const minLen = msg.match(/at least (\d+) character/i);
      if (minLen) return `至少需要 ${minLen[1]} 个字符`;
      if (/field required/i.test(msg)) return "必填";
      if (/value is not a valid/i.test(msg)) return "格式无效";
      return msg;
    };
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object" || !("msg" in item)) {
          return "";
        }
        const row = item as { loc?: unknown[]; msg: string };
        const rawField = Array.isArray(row.loc)
          ? row.loc.filter((part) => part !== "body" && part !== "query" && part !== "path").map(String).join(".")
          : "";
        const fieldKey = rawField.split(".").pop() || rawField;
        const field = fieldLabels[fieldKey] || fieldLabels[rawField] || rawField;
        const msg = translateMsg(row.msg);
        return field ? `${field}${msg === "不能为空" || msg === "必填" ? msg : `：${msg}`}` : msg;
      })
      .filter(Boolean);
    if (messages.length) {
      return messages.join("；");
    }
  }
  return `请求失败 (${status})`;
}

export async function req<T>(
  path: string,
  init?: RequestInit,
  options?: { clearTokenOn401?: boolean; timeoutMs?: number },
): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (!headers.has("Content-Type") && init?.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = authStore.getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const timeoutMs = options?.timeoutMs ?? 30_000;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  // Preserve caller AbortSignal (e.g. route leave) while still enforcing timeout.
  const callerSignal = init?.signal;
  if (callerSignal) {
    if (callerSignal.aborted) {
      window.clearTimeout(timer);
      throw new Error("请求已取消");
    }
    callerSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  try {
    const { signal: _ignored, headers: _ignoredHeaders, ...rest } = init ?? {};
    const res = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      headers,
      signal: controller.signal,
    });
    const data = await parseResponseJson(res);
    const clearTokenOn401 = options?.clearTokenOn401 !== false;
    if (clearTokenOn401 && res.status === 401 && token && authStore.getToken() === token) {
      authStore.clear();
    }
    if (!res.ok) {
      throw new Error(formatApiError(data, res.status));
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (callerSignal?.aborted) {
        throw new Error("请求已取消");
      }
      throw new Error(
        timeoutMs > 60_000
          ? "请求超时：操作耗时较长（AI 生成或压测下发）。请缩短压测时长，或关闭分布式后重试"
          : "请求超时，请确认后端 API 已启动且未卡死（默认 http://127.0.0.1:8002）",
      );
    }
    if (error instanceof TypeError) {
      throw new Error("无法连接后端 API，请确认服务已启动（默认 http://127.0.0.1:8002）");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function reqBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = authStore.getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE_URL}${path}`, { headers });
  if (res.status === 401 && token && authStore.getToken() === token) {
    authStore.clear();
  }
  if (!res.ok) {
    let message = "文件下载失败，请稍后重试";
    try {
      const data = await parseResponseJson(res);
      message = formatApiError(data, res.status) || message;
    } catch (error) {
      if (error instanceof Error && error.message) {
        message = error.message;
      }
    }
    throw new Error(message);
  }
  return res.blob();
}

export async function reqFormData<T>(
  path: string,
  form: FormData,
  init?: RequestInit,
  options?: { timeoutMs?: number },
): Promise<T> {
  const token = authStore.getToken();
  const timeoutMs = options?.timeoutMs ?? 120_000;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const callerSignal = init?.signal;
  if (callerSignal) {
    if (callerSignal.aborted) {
      window.clearTimeout(timer);
      throw new Error("请求已取消");
    }
    callerSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  try {
    const { signal: _ignored, headers: _ignoredHeaders, ...rest } = init ?? {};
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      ...rest,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
      signal: controller.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && token && authStore.getToken() === token) {
      authStore.clear();
    }
    if (!res.ok) {
      throw new Error(formatApiError(data as Record<string, unknown>, res.status) || "请求失败，请稍后重试");
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (callerSignal?.aborted) {
        throw new Error("请求已取消");
      }
      throw new Error("请求超时，AI 分析耗时较长，请稍后重试");
    }
    if (error instanceof TypeError) {
      throw new Error("无法连接后端 API，请确认服务已启动（默认 http://127.0.0.1:8002）");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function fetchAuthedText(path: string): Promise<string> {
  const headers = new Headers();
  const token = authStore.getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE_URL}${path}`, { headers });
  if (!res.ok) {
    const data = await parseResponseJson(res).catch(() => ({}));
    throw new Error(formatApiError(data, res.status) || "内容加载失败，请稍后重试");
  }
  return res.text();
}

export function openAuthedHtml(path: string) {
  const token = authStore.getToken();
  void fetch(`${BASE_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    .then((res) => res.text())
    .then((html) => {
      const w = window.open("", "_blank");
      if (w) {
        w.document.write(html);
        w.document.close();
      }
    });
}

export async function downloadBlob(path: string, filename: string) {
  const blob = await reqBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
