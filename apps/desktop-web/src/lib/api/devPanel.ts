import { callBridge, whenBridgeReady } from "../bridge/adapter";
import type { DevContext, DevDataInfo, DevDataOperation, DevDataTarget, DevWorktreeList } from "../bridge/types.dev";

/** Typed facade for the dev panel. Every call throws with the bridge's own message on failure. */

export const DEV_CONTEXT_QUERY_KEY = ["dev", "context"] as const;

export async function fetchDevContext(): Promise<DevContext> {
  await whenBridgeReady();
  const response = await callBridge("dev_get_context", {});
  if (!response.ok) throw new Error(response.error);
  return response;
}

/** Asks the dev supervisor to restart the app; the window closes right after it resolves. */
export async function restartDevApp(): Promise<void> {
  const response = await callBridge("dev_restart", {});
  if (!response.ok) throw new Error(response.error);
}

/** Resolves with the state the dev supervisor confirmed. */
export async function setDevAutoRestart(enabled: boolean): Promise<boolean> {
  const response = await callBridge("dev_set_auto_restart", { enabled });
  if (!response.ok) throw new Error(response.error);
  return response.auto_restart;
}

export const DEV_WORKTREES_QUERY_KEY = ["dev", "worktrees"] as const;

export async function fetchDevWorktrees(): Promise<DevWorktreeList> {
  await whenBridgeReady();
  const response = await callBridge("dev_list_worktrees", {});
  if (!response.ok) throw new Error(response.error);
  return response;
}

export const DEV_DATA_QUERY_KEY = ["dev", "data"] as const;

export async function fetchDevDataInfo(): Promise<DevDataInfo> {
  await whenBridgeReady();
  const response = await callBridge("dev_get_data_info", {});
  if (!response.ok) throw new Error(response.error);
  return response;
}

/**
 * Resolves once the dev supervisor accepted. The window then reopens on the
 * worktree, right away or, with `installing`, after its dependencies install.
 */
export async function switchDevWorktree(path: string): Promise<{ worktree: string; installing: boolean }> {
  const response = await callBridge("dev_switch_worktree", { path });
  if (!response.ok) throw new Error(response.error);
  return { worktree: response.worktree, installing: response.installing };
}

/**
 * Hands a dev data action to the dev supervisor; the window closes right after
 * it resolves. `confirm` repeats the target for a permanent delete.
 */
export async function runDevDataAction(operation: DevDataOperation, target: DevDataTarget, confirm = ""): Promise<void> {
  const response =
    operation === "backup"
      ? await callBridge("dev_move_data_to_backup", { target })
      : operation === "restore"
        ? await callBridge("dev_restore_data_backup", { target })
        : await callBridge("dev_delete_data", { target, confirm });
  if (!response.ok) throw new Error(response.error);
}
