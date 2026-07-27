import type { RouteLocationNormalized } from "vue-router";
import { usePlatformStore } from "../state/platform";

export type RoutePermissionDenied = {
  required: string[];
};

export function getRoutePermissionDenied(to: RouteLocationNormalized): RoutePermissionDenied | null {
  const store = usePlatformStore();
  const required: string[] = [];

  for (const record of to.matched) {
    const { permission, permissions, permissionMode = "any" } = record.meta;
    if (permission) {
      if (!store.hasPermission(permission)) {
        required.push(permission);
      }
      continue;
    }
    if (permissions?.length) {
      const ok =
        permissionMode === "all"
          ? permissions.every((code) => store.hasPermission(code))
          : permissions.some((code) => store.hasPermission(code));
      if (!ok) {
        required.push(...permissions);
      }
    }
  }

  return required.length ? { required: [...new Set(required)] } : null;
}

export function formatRequiredPermissions(codes: string[]) {
  return codes.join(" / ");
}
