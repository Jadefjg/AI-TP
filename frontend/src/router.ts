import { createRouter, createWebHistory } from "vue-router";
import { authStore } from "./api/auth-store";
import { formatRequiredPermissions, getRoutePermissionDenied } from "./router/permissions";
import { usePlatformStore } from "./state/platform";
import LoginPage from "./pages/LoginPage.vue";
import RegisterPage from "./pages/RegisterPage.vue";
import ShellLayout from "./layouts/ShellLayout.vue";

const DashboardPage = () => import("./pages/DashboardPage.vue");
const TasksPage = () => import("./pages/TasksPage.vue");
const RunDetailPage = () => import("./pages/RunDetailPage.vue");
const ProjectsPage = () => import("./pages/ProjectsPage.vue");
const ProjectLayout = () => import("./pages/project/ProjectLayout.vue");
const ProjectCasesPage = () => import("./pages/project/ProjectCasesPage.vue");
const ProjectAiPage = () => import("./pages/project/ProjectAiPage.vue");
const ProjectRunsPage = () => import("./pages/project/ProjectRunsPage.vue");
const ProjectReportsPage = () => import("./pages/project/ProjectReportsPage.vue");
const ProjectWorkbenchPage = () => import("./pages/project/ProjectWorkbenchPage.vue");
const ProjectIntegrationsPage = () => import("./pages/project/ProjectIntegrationsPage.vue");
const ProjectUiPage = () => import("./pages/project/ProjectUiPage.vue");
const RequirementsPage = () => import("./pages/RequirementsPage.vue");
const CasesPage = () => import("./pages/CasesPage.vue");
const UiManagementPage = () => import("./pages/UiManagementPage.vue");
const ApiManagementPage = () => import("./pages/ApiManagementPage.vue");
const PerfManagementPage = () => import("./pages/PerfManagementPage.vue");
const SecurityManagementPage = () => import("./pages/SecurityManagementPage.vue");
const TenantPage = () => import("./pages/TenantPage.vue");
const SystemUsersLayout = () => import("./pages/SystemUsersLayout.vue");
const RbacUserList = () => import("./pages/rbac/RbacUserList.vue");
const RbacDepartments = () => import("./pages/rbac/RbacDepartments.vue");
const RbacRoles = () => import("./pages/rbac/RbacRoles.vue");
const RbacPermissions = () => import("./pages/rbac/RbacPermissions.vue");
const SystemPage = () => import("./pages/SystemPage.vue");
const LogsPage = () => import("./pages/LogsPage.vue");
const SettingsPage = () => import("./pages/SettingsPage.vue");
const AiPromptsPage = () => import("./pages/AiPromptsPage.vue");
const K6WorkersPage = () => import("./pages/K6WorkersPage.vue");
const ForbiddenPage = () => import("./pages/ForbiddenPage.vue");

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: LoginPage,
      meta: { requiresAuth: false },
    },
    {
      path: "/register",
      name: "register",
      component: RegisterPage,
      meta: { requiresAuth: false },
    },
    {
      path: "/",
      component: ShellLayout,
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: "/dashboard" },
        {
          path: "dashboard",
          name: "dashboard",
          component: DashboardPage,
          meta: { requiresAuth: true, permission: "dashboard.read" },
        },
        {
          path: "tasks",
          name: "tasks",
          component: TasksPage,
          meta: { requiresAuth: true, permission: "run.read" },
        },
        {
          path: "tasks/:runId",
          name: "task-run-detail",
          component: RunDetailPage,
          meta: { requiresAuth: true, permission: "run.read" },
        },
        {
          path: "runs/:runId",
          redirect: (to) => ({ name: "task-run-detail", params: { runId: to.params.runId } }),
        },
        {
          path: "projects",
          name: "projects",
          component: ProjectsPage,
          meta: { requiresAuth: true, permission: "project.read" },
        },
        {
          path: "requirements",
          name: "requirements",
          component: RequirementsPage,
          meta: { requiresAuth: true, permission: "ai.read" },
        },
        {
          path: "cases",
          name: "cases",
          component: CasesPage,
          meta: { requiresAuth: true, permission: "case.read" },
        },
        {
          path: "ui-management",
          name: "ui-management",
          component: UiManagementPage,
          meta: { requiresAuth: true, permission: "ai.read" },
        },
        {
          path: "interface-management",
          name: "interface-management",
          component: ApiManagementPage,
          meta: { requiresAuth: true, permission: "ai.read" },
        },
        {
          path: "perf-management",
          name: "perf-management",
          component: PerfManagementPage,
          meta: { requiresAuth: true, permission: "ai.read" },
        },
        {
          path: "security-management",
          name: "security-management",
          component: SecurityManagementPage,
          meta: { requiresAuth: true, permission: "ai.read" },
        },
        {
          path: "projects/:id",
          component: ProjectLayout,
          meta: { requiresAuth: true, permission: "project.read" },
          children: [
            { path: "", redirect: { name: "project-cases" } },
            {
              path: "cases",
              name: "project-cases",
              component: ProjectCasesPage,
              meta: { requiresAuth: true, permission: "case.read" },
            },
            {
              path: "ai",
              name: "project-ai",
              component: ProjectAiPage,
              meta: { requiresAuth: true, permission: "ai.read" },
            },
            {
              path: "runs",
              name: "project-runs",
              component: ProjectRunsPage,
              meta: { requiresAuth: true, permission: "run.read" },
            },
            {
              path: "reports",
              name: "project-reports",
              component: ProjectReportsPage,
              meta: { requiresAuth: true, permission: "run.read" },
            },
            {
              path: "workbench",
              name: "project-workbench",
              component: ProjectWorkbenchPage,
              meta: { requiresAuth: true, permission: "workbench.read" },
            },
            {
              path: "integrations",
              name: "project-integrations",
              component: ProjectIntegrationsPage,
              meta: { requiresAuth: true, permission: "integration.ci.read" },
            },
            {
              path: "ui",
              name: "project-ui",
              component: ProjectUiPage,
              meta: { requiresAuth: true, permission: "case.read" },
            },
          ],
        },
        {
          path: "projects/:id/legacy",
          name: "project-detail",
          redirect: (to) => ({ name: "project-cases", params: { id: to.params.id } }),
        },
        {
          path: "tenant",
          name: "tenant",
          component: TenantPage,
          meta: {
            requiresAuth: true,
            permissions: ["org.read", "org.member.read", "billing.read"],
            permissionMode: "any",
          },
        },
        {
          path: "billing/success",
          name: "billing-success",
          component: TenantPage,
          meta: {
            requiresAuth: true,
            permissions: ["org.read", "org.member.read", "billing.read"],
            permissionMode: "any",
          },
        },
        {
          path: "billing/cancel",
          name: "billing-cancel",
          component: TenantPage,
          meta: {
            requiresAuth: true,
            permissions: ["org.read", "org.member.read", "billing.read"],
            permissionMode: "any",
          },
        },
        {
          path: "system-users",
          name: "system-users",
          component: SystemUsersLayout,
          meta: { requiresAuth: true },
          children: [
            {
              path: "users",
              name: "system-users-users",
              component: RbacUserList,
              meta: { requiresAuth: true, permission: "user.manage" },
            },
            {
              path: "departments",
              name: "system-users-departments",
              component: RbacDepartments,
              meta: {
                requiresAuth: true,
                permissions: ["org.read", "user.manage"],
                permissionMode: "any",
              },
            },
            {
              path: "roles",
              name: "system-users-roles",
              component: RbacRoles,
              meta: { requiresAuth: true, permission: "role.manage" },
            },
            {
              path: "permissions",
              name: "system-users-permissions",
              component: RbacPermissions,
              meta: { requiresAuth: true, permission: "permission.manage" },
            },
          ],
        },
        { path: "rbac", redirect: { name: "system-users" } },
        {
          path: "system",
          name: "system",
          component: SystemPage,
          meta: { requiresAuth: true, permission: "system.read" },
        },
        {
          path: "logs",
          name: "logs",
          component: LogsPage,
          meta: { requiresAuth: true, permission: "logs.read" },
        },
        {
          path: "settings",
          name: "settings",
          component: SettingsPage,
          meta: { requiresAuth: true, permission: "settings.read" },
        },
        {
          path: "ai-prompts",
          name: "ai-prompts",
          component: AiPromptsPage,
          meta: { requiresAuth: true, permission: "prompt.read" },
        },
        {
          path: "k6-workers",
          name: "k6-workers",
          component: K6WorkersPage,
          meta: { requiresAuth: true, permission: "worker.read" },
        },
        {
          path: "forbidden",
          name: "forbidden",
          component: ForbiddenPage,
          meta: { requiresAuth: true },
        },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const store = usePlatformStore();
  const token = authStore.getToken();
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth);

  if (to.name === "login" || to.name === "register") {
    if (!token) {
      return true;
    }
    if (!store.authReady.value) {
      await store.bootstrapSession();
    }
    if (store.isAuthenticated.value) {
      const redirect = typeof to.query.redirect === "string" ? to.query.redirect : "/dashboard";
      return redirect;
    }
    return true;
  }

  if (requiresAuth && to.name !== "forbidden") {
    if (!token) {
      return { name: "login", query: { redirect: to.fullPath } };
    }
    if (!store.authReady.value) {
      await store.bootstrapSession();
    }
    if (!store.isAuthenticated.value || !authStore.getToken()) {
      return { name: "login", query: { redirect: to.fullPath } };
    }
    const denied = getRoutePermissionDenied(to);
    if (denied) {
      return {
        name: "forbidden",
        query: {
          from: to.fullPath,
          permission: formatRequiredPermissions(denied.required),
        },
      };
    }
    return true;
  }

  if (requiresAuth && !token) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  return true;
});

const CHUNK_RELOAD_FLAG = "ai-tp:chunk-reload";

router.onError((error, to) => {
  const message = error instanceof Error ? error.message : String(error);
  const isChunkLoadFailure =
    /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk .* failed/i.test(
      message,
    );
  if (!isChunkLoadFailure || sessionStorage.getItem(CHUNK_RELOAD_FLAG)) {
    return;
  }
  sessionStorage.setItem(CHUNK_RELOAD_FLAG, "1");
  const target = to.fullPath || window.location.pathname + window.location.search;
  window.location.assign(target.startsWith("/") ? target : `/${target}`);
});

export default router;
