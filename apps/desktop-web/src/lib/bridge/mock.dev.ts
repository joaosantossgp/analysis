import type { BridgeApi } from "./types";
import type {
  DevContext,
  DevDataActionResponse,
  DevDataInfo,
  DevDataOperation,
  DevDataTarget,
  DevDataTargetInfo,
} from "./types.dev";

/**
 * Mock-bridge scenarios for the dev panel. Pick one in `npm run dev:mock` with
 * `localStorage.setItem("cvm_mock_dev_context", "isolated")` and reload.
 * Simulated values only; never shown outside mock mode.
 */
export const MOCK_DEV_CONTEXT_SCENARIO_KEY = "cvm_mock_dev_context";

const SHARED: DevContext = {
  ok: true,
  worktree: "analisys",
  worktree_path: "C:\\Projects\\analisys",
  is_main_checkout: true,
  branch: "main",
  commit: "6b75561",
  dirty: false,
  git_error: null,
  data_mode: "shared",
  data_path: "C:\\Projects\\analisys\\data\\dev-runtime",
  supervised: true,
  auto_restart: true,
  pending_changes: 0,
};

export const MOCK_DEV_CONTEXTS = {
  shared: SHARED,
  isolated: {
    ...SHARED,
    worktree: "610-dev-panel",
    worktree_path: "C:\\Projects\\analisys\\.claude\\worktrees\\610-dev-panel",
    is_main_checkout: false,
    branch: "feat/610-dev-panel",
    commit: "a1b2c3d",
    dirty: true,
    data_mode: "isolated",
    data_path: "C:\\Projects\\analisys\\.claude\\worktrees\\610-dev-panel\\data\\dev-runtime",
    auto_restart: false,
    pending_changes: 2,
  },
} satisfies Record<string, DevContext>;

type Scenario = keyof typeof MOCK_DEV_CONTEXTS | "error";

function scenario(): Scenario {
  const stored = typeof window === "undefined" ? null : window.localStorage?.getItem(MOCK_DEV_CONTEXT_SCENARIO_KEY);
  return stored === "isolated" || stored === "error" ? stored : "shared";
}

export function createMockDevMethods(): Pick<BridgeApi, "dev_get_context" | "dev_restart" | "dev_set_auto_restart"> {
  let autoRestart: boolean | null = null;
  return {
    async dev_get_context() {
      const key = scenario();
      if (key === "error") return { ok: false, error: "Mock failure: the dev context could not be read." };
      const context = MOCK_DEV_CONTEXTS[key];
      return { ...context, auto_restart: autoRestart ?? context.auto_restart };
    },
    async dev_restart() {
      return { ok: true };
    },
    async dev_set_auto_restart({ enabled }) {
      autoRestart = enabled;
      return { ok: true, auto_restart: enabled };
    },
  };
}

// --- Dev data actions ---------------------------------------------------------

/** `localStorage.setItem("cvm_mock_dev_data", "unavailable")` previews the installed-app refusal. */
export const MOCK_DEV_DATA_SCENARIO_KEY = "cvm_mock_dev_data";

const MIB = 1024 * 1024;

function mockTarget(
  target: DevDataTarget,
  root: string,
  sizeBytes: number | null,
  shared: boolean,
  backupBytes: number | null = null,
): DevDataTargetInfo {
  return {
    target,
    path: target === "all" ? root : `${root}\\${target}`,
    exists: sizeBytes !== null,
    size_bytes: sizeBytes,
    shared,
    backup_path: `${root}.backup\\${target}`,
    backup_exists: backupBytes !== null,
    backup_size_bytes: backupBytes,
  };
}

const SHARED_ROOT = SHARED.data_path;
const ISOLATED_ROOT = MOCK_DEV_CONTEXTS.isolated.data_path;

export const MOCK_DEV_DATA = {
  shared: {
    ok: true,
    unavailable_reason: null,
    supervised: true,
    targets: [
      mockTarget("db", SHARED_ROOT, 15.2 * MIB, true, 14.8 * MIB),
      mockTarget("input", SHARED_ROOT, 2150 * MIB, true),
      mockTarget("all", SHARED_ROOT, 2166 * MIB, true),
    ],
    last_action: null,
  },
  isolated: {
    ok: true,
    unavailable_reason: null,
    supervised: true,
    targets: [
      mockTarget("db", ISOLATED_ROOT, 15.2 * MIB, false),
      mockTarget("input", SHARED_ROOT, 2150 * MIB, true),
      mockTarget("all", ISOLATED_ROOT, 15.6 * MIB, false),
    ],
    last_action: null,
  },
  unavailable: {
    ok: true,
    unavailable_reason:
      "Dev mode uses installed-app data (CVMANALYTICS_USE_RELEASE_DATA). Data actions never touch Documents\\CVMAnalytics.",
    supervised: true,
    targets: [],
    last_action: null,
  },
} satisfies Record<string, DevDataInfo>;

const DONE: Record<DevDataOperation, string> = {
  backup: "Moved {label} to backup",
  restore: "Restored the {label} backup",
  delete: "Deleted {label} permanently",
};
const LABEL: Record<DevDataTarget, string> = { db: "Database", input: "Downloaded CVM files", all: "Everything" };

/**
 * The real app closes and reopens after an action; the mock applies it in
 * memory, so closing and reopening the panel shows the result. Targets do not
 * affect each other here ("Everything" leaves the database row as it was).
 */
export function createMockDevDataMethods(): Pick<
  BridgeApi,
  "dev_get_data_info" | "dev_move_data_to_backup" | "dev_restore_data_backup" | "dev_delete_data"
> {
  let info: DevDataInfo | null = null;
  const current = (): DevDataInfo => {
    if (info) return info;
    const stored = typeof window === "undefined" ? null : window.localStorage?.getItem(MOCK_DEV_DATA_SCENARIO_KEY);
    const key = stored === "unavailable" ? "unavailable" : scenario() === "isolated" ? "isolated" : "shared";
    info = structuredClone(MOCK_DEV_DATA[key]);
    return info;
  };

  function act(operation: DevDataOperation, target: DevDataTarget, confirm?: string): DevDataActionResponse {
    const state = current();
    if (state.unavailable_reason) return { ok: false, status: "blocked", error: state.unavailable_reason };
    const item = state.targets.find((candidate) => candidate.target === target);
    if (!item) return { ok: false, error: `Unknown data target '${target}'.` };
    if (operation === "restore" ? !item.backup_exists : !item.exists) {
      return { ok: false, error: operation === "restore" ? `There is no ${LABEL[target]} backup.` : `${item.path} does not exist.` };
    }
    if (operation === "delete" && confirm !== target) return { ok: false, error: `Type ${target} to confirm the permanent delete.` };
    if (operation === "backup") {
      Object.assign(item, { backup_exists: true, backup_size_bytes: item.size_bytes, exists: false, size_bytes: null });
    } else if (operation === "restore") {
      Object.assign(item, { exists: true, size_bytes: item.backup_size_bytes, backup_exists: false, backup_size_bytes: null });
    } else {
      Object.assign(item, { exists: false, size_bytes: null });
    }
    state.last_action = {
      operation,
      target,
      ok: true,
      message: `${DONE[operation].replace("{label}", LABEL[target])} (${item.path}).`,
      finished_at: new Date().toISOString().slice(0, 19).replace("T", " "),
    };
    return { ok: true };
  }

  return {
    async dev_get_data_info() {
      if (scenario() === "error") return { ok: false, error: "Mock failure: dev data could not be read." };
      return structuredClone(current());
    },
    async dev_move_data_to_backup({ target }) {
      return act("backup", target);
    },
    async dev_restore_data_backup({ target }) {
      return act("restore", target);
    },
    async dev_delete_data({ target, confirm }) {
      return act("delete", target, confirm);
    },
  };
}
