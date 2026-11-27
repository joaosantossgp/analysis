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

/** One git worktree of the repository, as the dev panel's worktree switch lists it. */
export interface DevWorktree {
  /** Folder name. */
  name: string;
  path: string;
  /** null on a detached HEAD. */
  branch: string | null;
  is_main_checkout: boolean;
  /** The worktree this window runs. */
  active: boolean;
  /** A data-sensitive worktree: it runs on isolated dev data. */
  isolated_data: boolean;
  /**
   * Dependency manifests (`requirements.txt`, `apps/desktop-web/package-lock.json`)
   * that differ from the environment dev mode runs on. Empty: switchable without an install.
   */
  dependency_differences: string[];
}

export interface DevWorktreeList {
  ok: true;
  /** Main checkout first, in git's order. Worktrees removed on disk are left out. */
  worktrees: DevWorktree[];
  /** False when the app runs without the dev supervisor: no switching. */
  supervised: boolean;
  /** Why the last switch did not happen, or why the window fell back; null when there is nothing to report. */
  notice: string | null;
}

export type DevWorktreesResponse = DevWorktreeList | DevFailure;
export type DevSwitchWorktreeResponse = { ok: true; worktree: string } | DevFailure;

/** Dev data a data action works on: the database, the downloaded CVM files, or the whole data root. */
export type DevDataTarget = "db" | "input" | "all";
export type DevDataOperation = "backup" | "restore" | "delete";

export interface DevDataTargetInfo {
  target: DevDataTarget;
  path: string;
  exists: boolean;
  /** null when the folder does not exist. */
  size_bytes: number | null;
  /** Shared dev data: other worktrees use this folder too. */
  shared: boolean;
  /** The single backup slot of this target (`<data root>.backup/<target>`). */
  backup_path: string;
  backup_exists: boolean;
  backup_size_bytes: number | null;
}

/** Outcome of the last data action of this dev session, written by the dev supervisor. */
export interface DevDataActionOutcome {
  operation: DevDataOperation;
  target: DevDataTarget;
  ok: boolean;
  message: string;
  finished_at: string;
}

export interface DevDataInfo {
  ok: true;
  /** Why data actions are unavailable (installed-app data, custom CVM_DATA_DIR); null when allowed. */
  unavailable_reason: string | null;
  /** False when the app runs without the dev supervisor, which performs the actions. */
  supervised: boolean;
  /** Empty when data actions are unavailable. */
  targets: DevDataTargetInfo[];
  last_action: DevDataActionOutcome | null;
}

export type DevDataInfoResponse = DevDataInfo | DevFailure;
/** Accepted: the dev supervisor stops the app, performs the action and starts it again. */
export type DevDataActionResponse = { ok: true } | DevFailure;
