import "vue-router";

declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
    /** 单权限码，必须拥有 */
    permission?: string;
    /** 多权限码，配合 permissionMode */
    permissions?: string[];
    /** any：任一即可；all：全部需要。默认 any */
    permissionMode?: "any" | "all";
  }
}

export {};
