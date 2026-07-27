import {
  computed,
  inject,
  provide,
  reactive,
  ref,
  watch,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from "vue";
import { aiApi } from "../../../../api/ai";
import { useProjectScope } from "../../../../composables/useProjectScope";
import { DEFAULT_BASE_URL, DEFAULT_HEALTH_URL } from "../../../../constants/platformDefaults";
import { usePlatformStore } from "../../../../state/platform";

export type ProjectAiContext = {
  projectId: ComputedRef<number>;
  store: ReturnType<typeof usePlatformStore>;
  aiForm: {
    requirementText: string;
    openapiContent: string;
    caseInfo: string;
    apiInfo: string;
    bizDesc: string;
    apiDoc: string;
    apiParams: string;
    baseUrl: string;
    targetUrl: string;
    scanMethod: string;
    paramName: string;
    paramValue: string;
    perfDistributed: boolean;
    securityEngine: string;
    feedbackOriginal: string;
    feedbackCorrected: string;
    feedbackModule: string;
    bindCaseId: string;
  };
  hasAiExecute: ComputedRef<boolean>;
  hasAiRead: ComputedRef<boolean>;
  aiArtifacts: Ref<Array<Record<string, unknown>>>;
  apiAutomationArtifacts: ComputedRef<Array<Record<string, unknown>>>;
  securityJobs: Ref<Array<Record<string, unknown>>>;
  perfK6Jobs: Ref<Array<Record<string, unknown>>>;
  selectedPerfJobId: Ref<string>;
  pickArtifactRequest: Ref<number | null>;
  dslLastResult: Ref<Record<string, unknown> | null>;
  loadAiArtifacts: () => void;
  loadSecurityJobs: () => void;
  loadPerfK6Jobs: () => void;
  requestPickArtifact: (artifactId: number) => void;
  executeArtifact: (artifactId: number, moduleType: string) => Promise<void>;
};

const PROJECT_AI_KEY: InjectionKey<ProjectAiContext> = Symbol("projectAi");

export function provideProjectAiContext(): ProjectAiContext {
  const store = usePlatformStore();
  const { projectId } = useProjectScope();

  const aiForm = reactive({
    requirementText: "",
    openapiContent: "",
    caseInfo: "",
    apiInfo: "",
    bizDesc: "",
    apiDoc: "",
    apiParams: "",
    baseUrl: DEFAULT_BASE_URL,
    targetUrl: DEFAULT_HEALTH_URL,
    scanMethod: "GET",
    paramName: "q",
    paramValue: "test",
    perfDistributed: false,
    securityEngine: "builtin",
    feedbackOriginal: "",
    feedbackCorrected: "",
    feedbackModule: "functional_cases",
    bindCaseId: "",
  });

  const aiArtifacts = ref<Array<Record<string, unknown>>>([]);
  const securityJobs = ref<Array<Record<string, unknown>>>([]);
  const perfK6Jobs = ref<Array<Record<string, unknown>>>([]);
  const selectedPerfJobId = ref("");
  const pickArtifactRequest = ref<number | null>(null);
  const dslLastResult = ref<Record<string, unknown> | null>(null);

  const hasAiExecute = computed(() => store.hasPermission("ai.execute"));
  const hasAiRead = computed(() => store.hasPermission("ai.read"));
  const apiAutomationArtifacts = computed(() =>
    aiArtifacts.value.filter((a) => a.module_type === "api_automation"),
  );

  const loadAiArtifacts = () =>
    store.runBackground(async () => {
      if (!hasAiRead.value) return;
      aiArtifacts.value = (await aiApi.listAiArtifacts(projectId.value)) as Array<Record<string, unknown>>;
    });

  const loadSecurityJobs = () =>
    store.runBackground(async () => {
      if (!hasAiRead.value) return;
      securityJobs.value = await aiApi.listSecurityScanJobs(projectId.value);
    });

  const loadPerfK6Jobs = () =>
    store.runBackground(async () => {
      perfK6Jobs.value = await aiApi.listPerfK6Jobs(projectId.value);
    });

  const requestPickArtifact = (artifactId: number) => {
    pickArtifactRequest.value = artifactId;
  };

  const executeArtifact = async (artifactId: number, moduleType: string) => {
    if (moduleType === "api_automation") {
      const result = await aiApi.executeApiArtifact(projectId.value, artifactId, { baseUrl: aiForm.baseUrl });
      dslLastResult.value = result;
      requestPickArtifact(artifactId);
      store.setOut(result);
      return;
    }
    if (moduleType === "perf_plan") {
      const result = await aiApi.dispatchPerfArtifact(
        projectId.value,
        artifactId,
        aiForm.baseUrl,
        aiForm.perfDistributed,
      );
      store.setOut(result);
      await loadPerfK6Jobs();
      if (result.job_id) {
        selectedPerfJobId.value = String(result.job_id);
      }
      return;
    }
    if (moduleType === "security_scan") {
      const result = await aiApi.dispatchSecurityArtifact(projectId.value, artifactId, {
        target_url: aiForm.targetUrl,
        method: aiForm.scanMethod,
        query_params: { [aiForm.paramName]: aiForm.paramValue },
        engine: aiForm.securityEngine,
      });
      store.setOut(result);
      await loadSecurityJobs();
    }
  };

  const refreshAiData = () => {
    if (!store.authReady.value || !hasAiRead.value) return;
    void loadAiArtifacts();
    void loadSecurityJobs();
    void loadPerfK6Jobs();
  };

  watch([() => store.authReady.value, () => store.currentUser.value, projectId], refreshAiData, {
    immediate: true,
  });

  const ctx: ProjectAiContext = {
    projectId,
    store,
    aiForm,
    hasAiExecute,
    hasAiRead,
    aiArtifacts,
    apiAutomationArtifacts,
    securityJobs,
    perfK6Jobs,
    selectedPerfJobId,
    pickArtifactRequest,
    dslLastResult,
    loadAiArtifacts,
    loadSecurityJobs,
    loadPerfK6Jobs,
    requestPickArtifact,
    executeArtifact,
  };

  provide(PROJECT_AI_KEY, ctx);
  return ctx;
}

export function useProjectAiContext(): ProjectAiContext {
  const ctx = inject(PROJECT_AI_KEY);
  if (!ctx) {
    throw new Error("useProjectAiContext must be used within ProjectAiSection");
  }
  return ctx;
}

export type { ApiRegressionSet } from "../../../../types";
