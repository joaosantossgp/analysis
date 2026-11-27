import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchUpdateProgress, triggerApplyUpdate } from "@/lib/api/appStatus";
import type { UpdateProgressStatus } from "@/lib/bridge/types";

export const UPDATE_PROGRESS_KEY = ["update-progress"] as const;

const APPLY_ERRORS: Record<string, string> = {
  no_update_available: "No update is ready to install. Use Check now in Settings > App.",
  already_in_progress: "An update is already running.",
};

/** The updater reports idle before an install and error after a failed one; anything else is running. */
export function isUpdateApplying(progress: UpdateProgressStatus | null | undefined): boolean {
  return Boolean(progress && progress.status !== "idle" && progress.status !== "error");
}

export function updateProgressLabel(progress: UpdateProgressStatus | null): string {
  switch (progress?.status) {
    case "downloading":
      return "Downloading update...";
    case "validating":
      return "Verifying checksum...";
    case "extracting":
      return "Preparing files...";
    case "ready":
    case "swapping":
      return "Restarting into the new version...";
    default:
      return "Starting update...";
  }
}

/**
 * Install flow shared by the shell announcement and the diagnostics card:
 * starts `apply_update`, then polls `get_update_progress` (a local read) only
 * while it runs. A failed install leaves the running version in place.
 */
export function useUpdateApply(enabled = true) {
  const queryClient = useQueryClient();
  const progressQuery = useQuery({
    queryKey: UPDATE_PROGRESS_KEY,
    queryFn: fetchUpdateProgress,
    enabled,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => (isUpdateApplying(query.state.data) ? 1_000 : false),
  });
  const apply = useMutation({
    mutationFn: async () => {
      const result = await triggerApplyUpdate();
      if (!result.started) {
        throw new Error(APPLY_ERRORS[result.error ?? ""] ?? result.error ?? "Could not start the update.");
      }
    },
    onMutate: () => {
      queryClient.setQueryData<UpdateProgressStatus>(UPDATE_PROGRESS_KEY, { status: "downloading", percent: 0, error: null });
    },
    // Re-read the updater either way: a progress read started before the click may have overwritten "downloading".
    onSettled: () => queryClient.invalidateQueries({ queryKey: UPDATE_PROGRESS_KEY }),
  });

  const progress = progressQuery.data ?? null;
  return {
    progress,
    applying: isUpdateApplying(progress),
    error:
      apply.error?.message ??
      (progress?.status === "error" ? progress.error || "The update failed." : null) ??
      (progressQuery.error ? String(progressQuery.error) : null),
    start: () => apply.mutate(),
  };
}
