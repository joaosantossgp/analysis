import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEV_CONTEXT_QUERY_KEY, fetchDevContext, restartDevApp, setDevAutoRestart } from "@/lib/api/devPanel";
import { MOCK_DEV_CONTEXTS } from "@/lib/bridge/mock.dev";
import type { DevContext } from "@/lib/bridge/types.dev";

import { DevPanel } from "./DevPanel";
import { devPanelOpenReducer, resolveDevPanelKey } from "./devPanelState";
import { DEV_PANEL_SECTIONS } from "./sections";

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
    expect(DEV_PANEL_SECTIONS.map((section) => section.id)).toEqual(["context", "worktrees", "restart", "tools"]);
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
