import type { BridgeApi } from "./types";
import type { DevContext } from "./types.dev";

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
