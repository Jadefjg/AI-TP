import type { RequestOption, UploadRequest } from "@arco-design/web-vue/es/upload/interfaces";

/** 手动上传模式：阻止 a-upload 向当前页面 URL 发 POST（action 默认为空会打到 /requirements 等路由） */
export function stubArcoUploadRequest(option: RequestOption): UploadRequest {
  option.onSuccess?.({});
  return {
    abort() {},
  };
}

export function resolveUploadFile(item: { file?: File } | null | undefined): File | null {
  return item?.file ?? null;
}
