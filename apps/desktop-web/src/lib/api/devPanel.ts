import { callBridge, whenBridgeReady } from "../bridge/adapter";
import type { DevContext, DevWorktreeList } from "../bridge/types.dev";

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

/** Resolves with the worktree name once the dev supervisor accepted; the window then reopens on it. */
export async function switchDevWorktree(path: string): Promise<string> {
  const response = await callBridge("dev_switch_worktree", { path });
  if (!response.ok) throw new Error(response.error);
  return response.worktree;
}
