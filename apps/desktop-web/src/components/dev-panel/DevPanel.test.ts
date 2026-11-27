import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEV_CONTEXT_QUERY_KEY,
  DEV_DATA_QUERY_KEY,
  fetchDevContext,
  fetchDevDataInfo,
  restartDevApp,
  runDevDataAction,
  setDevAutoRestart,
} from "@/lib/api/devPanel";
import { MOCK_DEV_CONTEXTS, MOCK_DEV_DATA } from "@/lib/bridge/mock.dev";
import type { DevContext, DevDataInfo, DevDataOperation, DevDataTargetInfo } from "@/lib/bridge/types.dev";

import { DevPanel } from "./DevPanel";
import { devPanelOpenReducer, resolveDevPanelKey } from "./devPanelState";
import { DEV_PANEL_SECTIONS } from "./sections";
import { DataActionConfirm, formatBytes } from "./sections/DevDataSection";

const NO_MODIFIERS = { altKey: false, ctrlKey: false, metaKey: false, shiftKey: false };

function client(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function render(queryClient: QueryClient, open = true): string {
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(MemoryRouter, null, createElement(DevPanel, { defaultOpen: open })),
    ),
  );
}

function renderWith(context: DevContext): string {
  const queryClient = client();
  queryClient.setQueryData(DEV_CONTEXT_QUERY_KEY, context);
  return render(queryClient);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("dev panel open and close", () => {
  it("starts as a closed dot", () => {
    const html = render(client(), false);

    expect(html).toContain('aria-label="Dev panel"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('role="dialog"');
  });

  it("opens and closes by clicking the dot, and closes from the close control", () => {
    expect(devPanelOpenReducer(false, "toggle")).toBe(true);
    expect(devPanelOpenReducer(true, "toggle")).toBe(false);
    expect(devPanelOpenReducer(true, "close")).toBe(false);
    expect(devPanelOpenReducer(false, "close")).toBe(false);
  });

  it("shows the panel with a close control once open", () => {
    const html = render(client());

    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-label="Close dev panel"');
  });

  it("toggles with Ctrl+Shift+D whether open or closed", () => {
    const chord = { ...NO_MODIFIERS, ctrlKey: true, shiftKey: true, key: "D" };

    expect(resolveDevPanelKey(chord, false)).toBe("toggle");
    expect(resolveDevPanelKey(chord, true)).toBe("toggle");
  });

  it("closes with Escape only while open", () => {
    const escape = { ...NO_MODIFIERS, key: "Escape" };

    expect(resolveDevPanelKey(escape, true)).toBe("close");
    expect(resolveDevPanelKey(escape, false)).toBeNull();
  });

  it("leaves Ctrl+Alt+D (design system) and plain keys alone", () => {
    expect(resolveDevPanelKey({ ...NO_MODIFIERS, ctrlKey: true, altKey: true, key: "d" }, false)).toBeNull();
    expect(resolveDevPanelKey({ ...NO_MODIFIERS, ctrlKey: true, key: "d" }, false)).toBeNull();
    expect(resolveDevPanelKey({ ...NO_MODIFIERS, key: "d" }, true)).toBeNull();
  });
});

describe("dev panel context", () => {
  it("shows what the window is running on shared dev data", () => {
    const html = renderWith(MOCK_DEV_CONTEXTS.shared);

    expect(html).toContain("analisys");
    expect(html).toContain("Main checkout");
    expect(html).toContain("main");
    expect(html).toContain("6b75561");
    expect(html).toContain("No uncommitted changes");
    expect(html).toContain("Shared dev data");
    expect(html).toContain("C:\\Projects\\analisys\\data\\dev-runtime");
    expect(html).not.toContain("Isolated data");
  });

  it("flags a data-sensitive worktree with uncommitted changes", () => {
    const html = renderWith(MOCK_DEV_CONTEXTS.isolated);

    expect(html).toContain("610-dev-panel");
    expect(html).toContain("feat/610-dev-panel");
    expect(html).toContain("a1b2c3d");
    expect(html).toContain("Uncommitted changes");
    expect(html).toContain("Isolated data");
    expect(html).not.toContain("Main checkout");
  });

  it("keeps git values missing and says why when git cannot answer", () => {
    const html = renderWith({
      ...MOCK_DEV_CONTEXTS.shared,
      branch: null,
      commit: null,
      dirty: null,
      git_error: "git not found",
    });

    expect(html).toContain("Git state unavailable");
    expect(html).toContain("git not found");
    expect(html).not.toContain("No uncommitted changes");
    expect(html).not.toContain("Detached HEAD");
  });

  it("shows a loading state before the context arrives", () => {
    expect(render(client())).toContain("Reading dev context…");
  });

  it("shows the bridge error with a retry", async () => {
    // A static render would otherwise show the refetch on mount instead of the failed state.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false } } });
    await queryClient.prefetchQuery({
      queryKey: DEV_CONTEXT_QUERY_KEY,
      queryFn: () => Promise.reject(new Error("git worktree list failed")),
    });

    const html = render(queryClient);

    expect(html).toContain("Dev context unavailable");
    expect(html).toContain("git worktree list failed");
    expect(html).toContain("retry");
    expect(html).toContain("Restart app");
  });
});

describe("dev panel restart controls and tools", () => {
  it("shows automatic restart on with a restart button", () => {
    const html = renderWith(MOCK_DEV_CONTEXTS.shared);

    expect(html).toContain("Restart app");
    expect(html).toMatch(/<input[^>]*type="checkbox"[^>]*checked=""/);
    expect(html).toContain("Automatic restart is on");
  });

  it("shows automatic restart off and the Python changes it is holding back", () => {
    const html = renderWith(MOCK_DEV_CONTEXTS.isolated);

    expect(html).not.toMatch(/<input[^>]*checked=""/);
    expect(html).toContain("Automatic restart is off");
    expect(html).toContain("A new --dev launch turns it back on.");
    expect(html).toContain("2 changed Python files not loaded yet.");
  });

  it("disables the controls when no dev supervisor is running", () => {
    const html = renderWith({ ...MOCK_DEV_CONTEXTS.shared, supervised: false, auto_restart: null, pending_changes: null });

    expect(html).toContain("No dev supervisor");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Restart app/);
    expect(html).toMatch(/<input[^>]*type="checkbox"[^>]*disabled=""/);
  });

  it("links to the data-ops dev page", () => {
    expect(render(client())).toContain('href="/dev/data-ops"');
  });

  it("builds the panel from one file per section", () => {
    expect(DEV_PANEL_SECTIONS.map((section) => section.id)).toEqual(["context", "worktrees", "restart", "data", "tools"]);
  });
});

describe("dev panel outside dev mode", () => {
  it("exists in a Vite dev build", async () => {
    expect((await import("./index")).LazyDevPanel).not.toBeNull();
  });

  it("is absent from a production build", async () => {
    vi.stubEnv("DEV", false);
    vi.resetModules();

    expect((await import("./index")).LazyDevPanel).toBeNull();
  });
});

describe("dev panel bridge facade", () => {
  it("reads the context and drives the restart controls through the mock bridge", async () => {
    vi.stubEnv("VITE_MOCK_BRIDGE", "1");
    vi.stubGlobal("window", {});

    await expect(fetchDevContext()).resolves.toEqual(MOCK_DEV_CONTEXTS.shared);
    await expect(setDevAutoRestart(false)).resolves.toBe(false);
    await expect(fetchDevContext()).resolves.toMatchObject({ auto_restart: false });
    await expect(restartDevApp()).resolves.toBeUndefined();
  });

  it("turns a refusal from the bridge into an error with its message", async () => {
    const refusal = { ok: false, status: "blocked", status_reason_code: "dev_mode_only", error: "Dev tools are available only in dev mode." };
    const api = { ping: vi.fn(), dev_get_context: vi.fn(async () => refusal), dev_restart: vi.fn(async () => refusal), dev_set_auto_restart: vi.fn(async () => refusal) };
    vi.stubGlobal("window", { pywebview: { api } });

    await expect(fetchDevContext()).rejects.toThrow("Dev tools are available only in dev mode.");
    await expect(restartDevApp()).rejects.toThrow("only in dev mode");
    await expect(setDevAutoRestart(true)).rejects.toThrow("only in dev mode");
    expect(api.dev_set_auto_restart).toHaveBeenCalledWith({ enabled: true });
  });
});

// --- Dev data actions (#614) ---------------------------------------------------

const SHARED_WARNING = "Shared dev data: this affects every worktree that uses it.";

function renderWithData(data: DevDataInfo): string {
  const queryClient = client();
  queryClient.setQueryData(DEV_CONTEXT_QUERY_KEY, MOCK_DEV_CONTEXTS.shared);
  queryClient.setQueryData(DEV_DATA_QUERY_KEY, data);
  return render(queryClient);
}

function renderConfirm(operation: DevDataOperation, item: DevDataTargetInfo): string {
  return renderToStaticMarkup(createElement(DataActionConfirm, { operation, item, busy: false, onCancel() {}, onConfirm() {} }));
}

function disabledButtons(html: string, label: string): number {
  return (html.match(new RegExp(`<button[^>]*disabled=""[^>]*>${label}<`, "g")) ?? []).length;
}

const [SHARED_DB, SHARED_INPUT] = MOCK_DEV_DATA.shared.targets;

describe("dev panel data section", () => {
  it("lists the database, downloaded CVM files and everything with sizes, paths and backups", () => {
    const html = renderWithData(MOCK_DEV_DATA.shared);

    expect(html).toContain('aria-label="Dev data"');
    for (const label of ["Database", "Downloaded CVM files", "Everything"]) expect(html).toContain(label);
    expect(html).toContain("15.2 MB");
    expect(html).toContain("Backup: 14.8 MB");
    expect(html).toContain("2.10 GB");
    expect(html).toContain("No backup");
    expect(html).toContain("C:\\Projects\\analisys\\data\\dev-runtime\\db");
    expect(html).toContain(SHARED_WARNING);
    expect(disabledButtons(html, "Move to backup")).toBe(0);
    expect(disabledButtons(html, "Restore backup")).toBe(2);
    expect(disabledButtons(html, "Delete")).toBe(0);
  });

  it("says which targets of isolated dev data are shared", () => {
    const html = renderWithData(MOCK_DEV_DATA.isolated);

    expect(html).toContain("Shared folder: isolated dev data reads downloaded CVM files from shared dev data.");
    expect(html).toContain("This worktree&#x27;s own data; downloaded CVM files stay in the shared folder.");
    expect(html).not.toContain(SHARED_WARNING);
  });

  it("offers no action when dev mode points at installed-app data", () => {
    const html = renderWithData(MOCK_DEV_DATA.unavailable);

    expect(html).toContain("Data actions unavailable");
    expect(html).toContain("CVMANALYTICS_USE_RELEASE_DATA");
    expect(html).not.toContain("Move to backup");
    expect(html).not.toContain(">Delete<");
  });

  it("disables the actions without a dev supervisor", () => {
    const html = renderWithData({ ...MOCK_DEV_DATA.shared, supervised: false });

    expect(html).toContain("No dev supervisor");
    expect(disabledButtons(html, "Move to backup")).toBe(3);
    expect(disabledButtons(html, "Delete")).toBe(3);
  });

  it("shows the outcome of the last data action, a failure as an error", () => {
    const outcome = { operation: "backup", target: "db", finished_at: "2026-11-27 10:00:00" } as const;

    const done = renderWithData({ ...MOCK_DEV_DATA.shared, last_action: { ...outcome, ok: true, message: "Moved Database to backup (x)." } });
    expect(done).toContain("Last action (2026-11-27 10:00:00): Moved Database to backup (x).");

    const failed = renderWithData({
      ...MOCK_DEV_DATA.shared,
      last_action: { ...outcome, ok: false, message: "Data action failed: the folder is locked. Nothing was changed." },
    });
    expect(failed).toContain("Last data action failed (2026-11-27 10:00:00)");
    expect(failed).toContain("Nothing was changed.");
  });

  it("shows a loading state before the dev data arrives", () => {
    expect(render(client())).toContain("Reading dev data…");
  });

  it("formats sizes in binary units and keeps a missing size missing", () => {
    expect([formatBytes(null), formatBytes(512), formatBytes(15.2 * 1024 * 1024), formatBytes(2150 * 1024 * 1024)]).toEqual([
      "—",
      "512 B",
      "15.2 MB",
      "2.10 GB",
    ]);
  });
});

describe("dev data confirmation", () => {
  it("states the target, its path and size, the backup it replaces and the shared-data warning", () => {
    const html = renderConfirm("backup", SHARED_DB);

    expect(html).toContain("Move Database to backup?");
    expect(html).toContain("C:\\Projects\\analisys\\data\\dev-runtime\\db (15.2 MB)");
    expect(html).toContain("C:\\Projects\\analisys\\data\\dev-runtime.backup\\db (14.8 MB)");
    expect(html).toContain("The current backup (14.8 MB) is deleted and replaced.");
    expect(html).toContain(SHARED_WARNING);
    expect(html).toContain("reopens on its empty first-run state");
  });

  it("asks for the target name again before a permanent delete", () => {
    const html = renderConfirm("delete", SHARED_DB);

    expect(html).toContain("Delete Database permanently?");
    expect(html).toContain("This cannot be undone. The backup (14.8 MB) is kept.");
    expect(html).toMatch(/Type <code[^>]*>db<\/code> to confirm/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*background:var\(--color-state-err\)[^>]*>Delete permanently/);
  });

  it("says that restoring deletes current data", () => {
    const html = renderConfirm("restore", SHARED_DB);

    expect(html).toContain("Restore the Database backup?");
    expect(html).toContain("Current data (15.2 MB) is deleted and replaced with the backup.");
    expect(html).not.toContain("first-run");
  });

  it("promises no first-run state when only the downloads go", () => {
    expect(renderConfirm("backup", SHARED_INPUT)).not.toContain("first-run");
  });

  it("leaves the shared-data warning out for a worktree's own data", () => {
    expect(renderConfirm("delete", MOCK_DEV_DATA.isolated.targets[0])).not.toContain(SHARED_WARNING);
    expect(renderConfirm("delete", MOCK_DEV_DATA.isolated.targets[1])).toContain(SHARED_WARNING);
  });
});

describe("dev data bridge facade", () => {
  it("reads dev data and runs the actions through the mock bridge", async () => {
    vi.stubEnv("VITE_MOCK_BRIDGE", "1");
    vi.stubGlobal("window", {});

    await expect(fetchDevDataInfo()).resolves.toEqual(MOCK_DEV_DATA.shared);
    await expect(runDevDataAction("delete", "db")).rejects.toThrow("Type db to confirm");
    await expect(runDevDataAction("restore", "input")).rejects.toThrow("no Downloaded CVM files backup");
    await expect(runDevDataAction("backup", "db")).resolves.toBeUndefined();

    const after = await fetchDevDataInfo();
    expect(after.targets[0]).toMatchObject({ exists: false, size_bytes: null, backup_exists: true, backup_size_bytes: SHARED_DB.size_bytes });
    expect(after.last_action).toMatchObject({ operation: "backup", target: "db", ok: true });
  });

  it("turns a refusal from the bridge into an error with its message", async () => {
    const refusal = { ok: false, status: "blocked", status_reason_code: "dev_data_actions_unavailable", error: "Dev mode uses installed-app data." };
    const api = {
      ping: vi.fn(),
      dev_get_data_info: vi.fn(async () => refusal),
      dev_move_data_to_backup: vi.fn(async () => refusal),
      dev_restore_data_backup: vi.fn(async () => refusal),
      dev_delete_data: vi.fn(async () => refusal),
    };
    vi.stubGlobal("window", { pywebview: { api } });

    await expect(fetchDevDataInfo()).rejects.toThrow("Dev mode uses installed-app data.");
    await expect(runDevDataAction("backup", "all")).rejects.toThrow("installed-app data");
    await expect(runDevDataAction("restore", "input")).rejects.toThrow("installed-app data");
    await expect(runDevDataAction("delete", "db", "db")).rejects.toThrow("installed-app data");
    expect(api.dev_move_data_to_backup).toHaveBeenCalledWith({ target: "all" });
    expect(api.dev_delete_data).toHaveBeenCalledWith({ target: "db", confirm: "db" });
  });
});
