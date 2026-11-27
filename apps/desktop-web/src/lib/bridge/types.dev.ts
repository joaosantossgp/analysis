/**
 * Dev-only bridge contract behind the dev panel (`desktop/bridge_api/dev.py`).
 * Every method refuses in the packaged app with `status: "blocked"`.
 */

/** Which data the dev mode window reads and writes. Vocabulary: GLOSSARY.md, "Development". */
export type DevDataMode = "shared" | "isolated" | "full-copy" | "installed-app" | "custom";

export interface DevContext {
  ok: true;
  /** Folder name of the checkout this window runs. */
  worktree: string;
  worktree_path: string;
  is_main_checkout: boolean;
  /** null on a detached HEAD, or when git could not answer (see `git_error`). */
  branch: string | null;
  commit: string | null;
  /** Uncommitted changes, untracked files included. null when git could not answer. */
  dirty: boolean | null;
  git_error: string | null;
  data_mode: DevDataMode;
  data_path: string;
  /** False when the app runs without the dev supervisor: no restart controls. */
  supervised: boolean;
  auto_restart: boolean | null;
  /** Changed Python files the running app has not loaded yet. */
  pending_changes: number | null;
}

export interface DevFailure {
  ok: false;
  error: string;
  status?: "blocked";
  status_reason_code?: string;
}

export type DevContextResponse = DevContext | DevFailure;
export type DevRestartResponse = { ok: true } | DevFailure;
export type DevAutoRestartResponse = { ok: true; auto_restart: boolean } | DevFailure;
