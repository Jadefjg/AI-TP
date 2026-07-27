import { onUnmounted, ref, type Ref } from "vue";
import { runsApi } from "../api/runs";
import type { Run } from "../types";

type RunPollOptions = {
  intervalMs?: number;
  pauseWhenHidden?: boolean;
  onSettled?: () => void;
};

export function useRunPoll(currentRun: Ref<Run | null>, options?: RunPollOptions) {
  const intervalMs = options?.intervalMs ?? 2000;
  const pauseWhenHidden = options?.pauseWhenHidden ?? true;
  let timer: ReturnType<typeof setInterval> | null = null;
  const polling = ref(false);

  const stop = () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    polling.value = false;
  };

  const tick = async (runId: number) => {
    if (pauseWhenHidden && document.hidden) return;
    polling.value = true;
    try {
      const run = await runsApi.getRun(runId);
      currentRun.value = run;
      if (run.status !== "pending" && run.status !== "running") {
        stop();
        options?.onSettled?.();
      }
    } catch {
      stop();
    } finally {
      polling.value = false;
    }
  };

  const start = (runId: number) => {
    stop();
    polling.value = true;
    timer = setInterval(() => {
      void tick(runId);
    }, intervalMs);
  };

  onUnmounted(stop);

  return { start, stop, polling };
};
