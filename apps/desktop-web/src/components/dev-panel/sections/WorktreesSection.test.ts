import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEV_WORKTREES_QUERY_KEY, fetchDevWorktrees, switchDevWorktree } from "@/lib/api/devPanel";
import { MOCK_DEV_CONTEXT_SCENARIO_KEY, MOCK_DEV_WORKTREES } from "@/lib/bridge/mock.dev";
import type { DevWorktreeList } from "@/lib/bridge/types.dev";

import { NEEDS_OWN_DEPENDENCIES, section } from "./WorktreesSection";

function client(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false } } });
}

function render(queryClient: QueryClient): string {
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client: queryClient }, createElement(section.Component, { closePanel: () => {} })),
  );
}

function renderWith(list: Partial<DevWorktreeList> = {}): string {
  const queryClient = client();
  queryClient.setQueryData(DEV_WORKTREES_QUERY_KEY, {
    ok: true,
    worktrees: MOCK_DEV_WORKTREES,
    supervised: true,
    notice: null,
    ...list,
  });
  return render(queryClient);
}

/** The `<li>` of one worktree. */
function row(html: string, name: string): string {
  const match = html.match(new RegExp(`<li[^>]*>(?:(?!</li>).)*?${name}(?:(?!</li>).)*</li>`));
  if (!match) throw new Error(`no row for ${name}`);
  return match[0];
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("dev panel worktrees section", () => {
  it("lists every worktree with its branch, main checkout first", () => {
    const html = renderWith();

    const names = MOCK_DEV_WORKTREES.map((worktree) => html.indexOf(worktree.name));
    expect(names.every((position) => position >= 0)).toBe(true);
    expect([...names].sort((a, b) => a - b)).toEqual(names);
    expect(row(html, "analisys")).toContain("Main checkout");
    expect(row(html, "610-dev-panel")).toContain("feat/610-dev-panel");
    expect(row(html, "review-pr-640")).toContain("Detached HEAD");
  });

  it("marks the active worktree and gives it no switch button", () => {
    const active = row(renderWith(), "analisys");

    expect(active).toContain("Active");
    expect(active).not.toContain("Switch to analisys");
  });

  it("flags isolated dev data and lets a matching worktree be switched to", () => {
    const isolated = row(renderWith(), "610-dev-panel");

    expect(isolated).toContain("Isolated data");
    expect(isolated).toMatch(/<button(?![^>]*disabled)[^>]*aria-label="Switch to 610-dev-panel"/);
  });

  it("disables the switch to a worktree whose dependencies differ and says why", () => {
    const differs = row(renderWith(), "612-own-dependencies");

    expect(differs).toContain("Dependencies differ");
    expect(differs).toContain(NEEDS_OWN_DEPENDENCIES);
    expect(differs).toContain("apps/desktop-web/package-lock.json");
    expect(differs).toMatch(/<button[^>]*disabled=""[^>]*aria-label="Switch to 612-own-dependencies"/);
  });

  it("disables every switch without a dev supervisor", () => {
    const html = renderWith({ supervised: false });

    expect(html).toContain("No dev supervisor: switching is unavailable.");
    expect(row(html, "610-dev-panel")).toMatch(/<button[^>]*disabled=""/);
  });

  it("shows why the last switch did not happen", () => {
    const notice = "Switching to 610-dev-panel failed: the app exited with code 1 (traceback in the terminal). The window is back on analisys.";

    const html = renderWith({ notice });

    expect(html).toContain("Last worktree switch");
    expect(html).toContain(notice);
  });

  it("shows a loading state, then the bridge error with a retry", async () => {
    expect(render(client())).toContain("Listing worktrees…");

    const failed = client();
    await failed.prefetchQuery({
      queryKey: DEV_WORKTREES_QUERY_KEY,
      queryFn: () => Promise.reject(new Error("git worktree list failed")),
    });
    const html = render(failed);

    expect(html).toContain("Worktrees unavailable");
    expect(html).toContain("git worktree list failed");
    expect(html).toContain("retry");
  });
});

describe("worktrees bridge facade", () => {
  it("lists the worktrees and switches through the mock bridge", async () => {
    vi.stubEnv("VITE_MOCK_BRIDGE", "1");
    vi.stubGlobal("window", {});

    const list = await fetchDevWorktrees();
    expect(list.worktrees.map((worktree) => worktree.name)).toEqual(MOCK_DEV_WORKTREES.map((worktree) => worktree.name));
    expect(list.worktrees.filter((worktree) => worktree.active).map((worktree) => worktree.name)).toEqual(["analisys"]);

    await expect(switchDevWorktree(MOCK_DEV_WORKTREES[1].path)).resolves.toBe("610-dev-panel");
    const switched = await fetchDevWorktrees();
    expect(switched.worktrees.find((worktree) => worktree.active)?.name).toBe("610-dev-panel");
  });

  it("follows the mock scenario, including a failure", async () => {
    vi.stubEnv("VITE_MOCK_BRIDGE", "1");
    vi.stubGlobal("window", { localStorage: { getItem: (key: string) => (key === MOCK_DEV_CONTEXT_SCENARIO_KEY ? "error" : null) } });

    await expect(fetchDevWorktrees()).rejects.toThrow("git could not list the worktrees");
  });

  it("turns a refusal from the bridge into an error with its message", async () => {
    const refusal = { ok: false, error: `612-own-dependencies needs its own dependencies; supported in a later version.` };
    const api = { ping: vi.fn(), dev_switch_worktree: vi.fn(async () => refusal) };
    vi.stubGlobal("window", { pywebview: { api } });

    await expect(switchDevWorktree("C:\\wt")).rejects.toThrow("supported in a later version");
    expect(api.dev_switch_worktree).toHaveBeenCalledWith({ path: "C:\\wt" });
  });
});
