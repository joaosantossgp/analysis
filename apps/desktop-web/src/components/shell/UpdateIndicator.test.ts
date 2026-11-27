import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { isUpdateApplying, UPDATE_PROGRESS_KEY } from "@/hooks/useUpdateApply";
import { fetchStoredUpdateCheck, UPDATE_CHECK_KEY } from "@/lib/api/appStatus";
import { createMockBridge } from "@/lib/bridge/mock";
import { MOCK_UPDATE_CHECKS as C, MOCK_UPDATE_PROGRESS as P, MOCK_UPDATE_SCENARIO_KEY } from "@/lib/bridge/mock.status";
import type { UpdateCheckResult, UpdateProgressStatus } from "@/lib/bridge/types";

import { UpdateIndicator, UpdatePanelBody, updateCheckPollInterval, type UpdatePanelBodyProps } from "./UpdateIndicator";

function renderPill(check: UpdateCheckResult | null, progress: UpdateProgressStatus = P.idle): string {
  const client = new QueryClient();
  client.setQueryData(UPDATE_CHECK_KEY, check);
  client.setQueryData(UPDATE_PROGRESS_KEY, progress);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(UpdateIndicator)));
}

function renderPanel(overrides: Partial<UpdatePanelBodyProps>): string {
  const props: UpdatePanelBodyProps = {
    check: C.release_available,
    progress: P.idle,
    error: null,
    postponing: false,
    postponeError: null,
    onUpdate: () => {},
    onLater: () => {},
    ...overrides,
  };
  return renderToStaticMarkup(createElement(UpdatePanelBody, props));
}

const NOT_CHECKED: UpdateCheckResult = { available: false, status: "not_checked", channel: "releases", current_version: "0.29.2", checked_at: null };

describe("UpdateIndicator pill", () => {
  it("announces an available release with its version", () => {
    const html = renderPill(C.release_available);
    expect(html).toMatch(/Update <span class="normal-case">0\.30\.1<\/span>/);
    expect(html).not.toContain("pre-release");
    expect(html).toContain('aria-label="Software update: Release 0.30.1 available"');
    expect(html).toContain('aria-haspopup="dialog"');
  });

  it("marks an available pre-release as such", () => {
    const html = renderPill(C.prereleases);
    expect(html).toContain("0.30.0-rc.1");
    expect(html).toContain(" · pre-release");
    expect(html).toContain("Pre-release 0.30.0-rc.1 available");
  });

  it("shows install progress while the update downloads", () => {
    expect(renderPill(C.release_available, P.downloading)).toContain("Updating 42%");
  });

  it("says the update failed after a failed install", () => {
    expect(renderPill(C.release_available, P.error)).toContain("Update failed");
  });

  it.each([
    ["postponed", C.snoozed],
    ["offline (check failed)", C.offline],
    ["up to date", C.releases],
    ["not checked yet", NOT_CHECKED],
    ["browser preview", null],
  ] as const)("shows nothing when %s", (_label, check) => {
    expect(renderPill(check)).toBe("");
  });
});

describe("UpdatePanelBody", () => {
  it("names version and kind, links the publication page and offers Update now and Later", () => {
    const html = renderPanel({});
    expect(html).toContain("0.30.1</span> is available");
    expect(html).toContain("Release · installed <span class=\"font-mono\">0.29.2</span>");
    expect(html).toContain(`href="${C.release_available.release_url}"`);
    expect(html).toContain("Publication page");
    expect(html).toContain(">Update now<");
    expect(html).toContain(">Later<");
    expect(html).toContain("Downloads only after Update now");
    expect(html).not.toContain('role="progressbar"');
  });

  it("marks a pre-release and its stability notice", () => {
    const html = renderPanel({ check: C.prereleases });
    expect(html).toContain("Pre-release · installed");
    expect(html).toContain("may be less stable");
    // No publication page known: no dead link.
    expect(html).not.toContain("Publication page");
  });

  it("shows progress instead of the actions while downloading", () => {
    const html = renderPanel({ progress: P.downloading });
    expect(html).toContain('role="progressbar"');
    expect(html).toContain('aria-valuenow="42"');
    expect(html).toContain("Downloading update...");
    expect(html).toContain("restarts into 0.30.1");
    expect(html).not.toContain(">Update now<");
    expect(html).not.toContain(">Later<");
  });

  it("says what failed, that the current version keeps running, and offers a retry", () => {
    const html = renderPanel({ progress: P.error, error: P.error.error });
    expect(html).toContain('role="alert"');
    expect(html).toContain("Update failed: [mock] Simulated failure before the swap");
    expect(html).toContain("keeps running");
    expect(html).toContain(">Try again<");
    expect(html).toContain(">Later<");
  });

  it("keeps the offer and shows why Later failed", () => {
    const html = renderPanel({ postponeError: "no_update_info" });
    expect(html).toContain("Could not postpone the update: no_update_info");
    expect(html).toContain(">Update now<");
  });

  it("flags an offer kept from before a failed check", () => {
    expect(renderPanel({ check: { ...C.release_available, status: "available_cached" } })).toContain(
      "The last update check failed",
    );
  });
});

describe("update status reads never force a GitHub check", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads the stored check without force and never asks get_app_status", async () => {
    const api = {
      ping: vi.fn(),
      check_update: vi.fn(async () => C.release_available),
      get_app_status: vi.fn(),
    };
    vi.stubGlobal("window", Object.assign(new EventTarget(), { setInterval, clearInterval, setTimeout, clearTimeout, pywebview: { api } }));

    await expect(fetchStoredUpdateCheck()).resolves.toBe(C.release_available);
    expect(api.check_update).toHaveBeenCalledTimes(1);
    expect(api.check_update).toHaveBeenCalledWith({ force: false });
    expect(api.get_app_status).not.toHaveBeenCalled();
  });

  it("polls the stored check fast only while the startup check runs, and not at all in browser preview", () => {
    expect(updateCheckPollInterval(NOT_CHECKED)).toBe(5_000);
    expect(updateCheckPollInterval({ ...NOT_CHECKED, status: "unknown" })).toBe(5_000);
    expect(updateCheckPollInterval(C.release_available)).toBe(60_000);
    expect(updateCheckPollInterval(C.offline)).toBe(60_000);
    expect(updateCheckPollInterval(null)).toBe(false);
  });

  it("treats only running installer states as applying", () => {
    expect(isUpdateApplying(null)).toBe(false);
    expect(isUpdateApplying(P.idle)).toBe(false);
    expect(isUpdateApplying(P.error)).toBe(false);
    for (const status of ["downloading", "validating", "extracting", "ready", "swapping"]) {
      expect(isUpdateApplying({ status, percent: 50, error: null })).toBe(true);
    }
  });
});

describe("mock bridge update flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("downloads with progress, then fails without replacing anything", async () => {
    vi.stubGlobal("localStorage", { getItem: (key: string) => (key === MOCK_UPDATE_SCENARIO_KEY ? "release_available" : null) });
    const bridge = createMockBridge();

    expect(await bridge.check_update!()).toMatchObject({ available: true, version: "0.30.1", publication_kind: "release" });
    expect(await bridge.get_update_progress!()).toEqual(P.idle);
    expect(await bridge.apply_update!()).toEqual({ started: true });
    const seen: UpdateProgressStatus[] = [];
    for (let i = 0; i < 8; i += 1) seen.push(await bridge.get_update_progress!());
    expect(seen.map((p) => p.status)).toEqual(expect.arrayContaining(["downloading", "validating", "error"]));
    expect(seen).toContainEqual(P.downloading);
    expect(seen.at(-1)).toEqual(P.error);
  });

  it("postpones the offer with Later", async () => {
    vi.stubGlobal("localStorage", { getItem: () => "release_available" });
    const bridge = createMockBridge();

    expect(await bridge.snooze_update!()).toEqual({ ok: true });
    expect(await bridge.check_update!()).toMatchObject({ available: false, status: "snoozed", latest_version: "0.30.1" });
    expect(await bridge.apply_update!()).toEqual({ started: false, error: "no_update_available" });
  });

  it("refuses to apply when releases only is up to date", async () => {
    const bridge = createMockBridge();

    expect(await bridge.apply_update!()).toEqual({ started: false, error: "no_update_available" });
    expect(await bridge.snooze_update!()).toEqual({ ok: false, error: "no_update_info" });
  });
});
