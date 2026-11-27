import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEV_WORKTREES_QUERY_KEY, fetchDevWorktrees, switchDevWorktree } from "@/lib/api/devPanel";
import {
  createMockDevWorktreeMethods,
  MOCK_DEV_CONTEXT_SCENARIO_KEY,
  MOCK_DEV_INSTALL_SCENARIO_KEY,
  MOCK_DEV_WORKTREES,
  MOCK_INSTALL_STEPS,
} from "@/lib/bridge/mock.dev";
import type { DevWorktreeList } from "@/lib/bridge/types.dev";

import { formatElapsed, INSTALL_DURATION, section } from "./WorktreesSection";

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
    notice_detail: null,
    install: null,
    ...list,
  });
  return render(queryClient);
}

const OWN = MOCK_DEV_WORKTREES[2];

/** The `<li>` of one worktree. */
function row(html: string, name: string): string {
  const match = html.match(new RegExp(`<li[^>]*>(?:(?!</li>).)*?${name}(?:(?!</li>).)*</li>`));
  if (!match) throw new Error(`no row for ${name}`);
  return match[0];
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
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

  it("offers to install the dependencies of a worktree whose dependencies differ, and says how long it takes", () => {
    const differs = row(renderWith(), "612-own-dependencies");

    expect(differs).toContain("Dependencies differ");
    expect(differs).toContain(`Switching installs its own dependencies first (${INSTALL_DURATION}).`);
    expect(differs).toContain("requirements.txt, apps/desktop-web/package-lock.json");
    expect(differs).toMatch(
      /<button(?![^>]*disabled)[^>]*aria-label="Install dependencies and switch to 612-own-dependencies"[^>]*>Install &amp; switch</,
    );
    expect(differs).not.toContain("later version");
  });

  it("switches right away to a worktree whose own dependencies are already installed", () => {
    const html = renderWith({
      worktrees: MOCK_DEV_WORKTREES.map((worktree) => (worktree === OWN ? { ...worktree, installs_needed: [] } : worktree)),
    });
    const differs = row(html, "612-own-dependencies");

    expect(differs).toContain("Dependencies differ");
    expect(differs).toContain("Runs on its own installed dependencies.");
    expect(differs).toMatch(/<button(?![^>]*disabled)[^>]*aria-label="Switch to 612-own-dependencies"[^>]*>Switch</);
  });

  it("shows the install's current step and elapsed time, and holds every switch meanwhile", () => {
    const install = { worktree: OWN.path, name: OWN.name, step: "Installing Python packages", started_at: Date.now() / 1000 - 75 };

    const html = renderWith({ install });

    expect(html).toContain("Installing dependencies for 612-own-dependencies");
    expect(html).toContain("Installing Python packages…");
    expect(html).toContain("1:15 elapsed");
    expect(html).toContain("The window stays on analisys and reopens on 612-own-dependencies");
    expect(html).toMatch(/role="status"/);
    expect(row(html, "610-dev-panel")).toMatch(/<button[^>]*disabled=""/);
    expect(row(html, "612-own-dependencies")).toMatch(/<button[^>]*disabled=""/);
  });

  it("shows the failed command and the end of its output after a failed install", () => {
    const notice = "Installing dependencies for 612-own-dependencies failed; the window stays on analisys.";
    const detail = { command: "npm.cmd ci", exit_code: 1, output: "npm ERR! code ETARGET\nnpm ERR! notarget left-pad@99" };

    const html = renderWith({ notice, notice_detail: detail });

    expect(html).toContain("Last worktree switch");
    expect(html).toContain(notice);
    expect(html).toMatch(/role="alert"/);
    expect(html).toContain("<code");
    expect(html).toContain("npm.cmd ci");
    expect(html).toContain("(exit code 1)");
    expect(html).toMatch(/<pre[^>]*aria-label="Output of the failed install"[^>]*>npm ERR! code ETARGET\nnpm ERR! notarget left-pad@99<\/pre>/);
    expect(row(html, "612-own-dependencies")).toMatch(/<button(?![^>]*disabled)[^>]*aria-label="Install dependencies/);
  });

  it("formats elapsed seconds as minutes and seconds", () => {
    expect([0, 9, 75, 600].map(formatElapsed)).toEqual(["0:00", "0:09", "1:15", "10:00"]);
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

    await expect(switchDevWorktree(MOCK_DEV_WORKTREES[1].path)).resolves.toEqual({
      worktree: "610-dev-panel",
      installing: false,
    });
    const switched = await fetchDevWorktrees();
    expect(switched.worktrees.find((worktree) => worktree.active)?.name).toBe("610-dev-panel");
  });

  it("simulates an install in the mock bridge, then switches, and installs nothing the second time", async () => {
    vi.useFakeTimers({ now: new Date("2026-11-27T10:00:00Z") });
    vi.stubGlobal("window", {});
    const mock = createMockDevWorktreeMethods();
    const list = async () => {
      const response = await mock.dev_list_worktrees();
      if (!response.ok) throw new Error(response.error);
      return response;
    };

    expect(await mock.dev_switch_worktree({ path: OWN.path })).toEqual({ ok: true, worktree: OWN.name, installing: true });
    expect((await list()).install).toMatchObject({ name: OWN.name, step: "Creating Python environment" });
    expect(await mock.dev_switch_worktree({ path: MOCK_DEV_WORKTREES[1].path })).toMatchObject({
      ok: false,
      error: expect.stringContaining("still installing"),
    });

    vi.advanceTimersByTime(MOCK_INSTALL_STEPS[1][0] * 1000);
    expect((await list()).install?.step).toBe("Installing Python packages");

    vi.advanceTimersByTime(MOCK_INSTALL_STEPS.at(-1)![0] * 1000);
    const done = await list();
    expect(done.install).toBeNull();
    expect(done.worktrees.find((worktree) => worktree.active)?.name).toBe(OWN.name);
    expect(done.worktrees.find((worktree) => worktree.name === OWN.name)?.installs_needed).toEqual([]);

    await mock.dev_switch_worktree({ path: MOCK_DEV_WORKTREES[0].path });
    expect(await mock.dev_switch_worktree({ path: OWN.path })).toEqual({ ok: true, worktree: OWN.name, installing: false });
  });

  it("simulates a failed install that leaves the window where it was", async () => {
    vi.useFakeTimers({ now: new Date("2026-11-27T10:00:00Z") });
    vi.stubGlobal("window", { localStorage: { getItem: (key: string) => (key === MOCK_DEV_INSTALL_SCENARIO_KEY ? "fail" : null) } });
    const mock = createMockDevWorktreeMethods();

    await mock.dev_switch_worktree({ path: OWN.path });
    vi.advanceTimersByTime(MOCK_INSTALL_STEPS.at(-1)![0] * 1000);
    const response = await mock.dev_list_worktrees();

    if (!response.ok) throw new Error(response.error);
    expect(response.install).toBeNull();
    expect(response.worktrees.find((worktree) => worktree.active)?.name).toBe("analisys");
    expect(response.notice).toBe(`Installing dependencies for ${OWN.name} failed; the window stays on analisys.`);
    expect(response.notice_detail).toMatchObject({ command: "npm.cmd ci", exit_code: 1 });
  });

  it("follows the mock scenario, including a failure", async () => {
    vi.stubEnv("VITE_MOCK_BRIDGE", "1");
    vi.stubGlobal("window", { localStorage: { getItem: (key: string) => (key === MOCK_DEV_CONTEXT_SCENARIO_KEY ? "error" : null) } });

    await expect(fetchDevWorktrees()).rejects.toThrow("git could not list the worktrees");
  });

  it("turns a refusal from the bridge into an error with its message", async () => {
    const refusal = { ok: false, error: "Dependencies for 612-own-dependencies are still installing; switch again once they are ready." };
    const api = { ping: vi.fn(), dev_switch_worktree: vi.fn(async () => refusal) };
    vi.stubGlobal("window", { pywebview: { api } });

    await expect(switchDevWorktree("C:\\wt")).rejects.toThrow("still installing");
    expect(api.dev_switch_worktree).toHaveBeenCalledWith({ path: "C:\\wt" });
  });
});
