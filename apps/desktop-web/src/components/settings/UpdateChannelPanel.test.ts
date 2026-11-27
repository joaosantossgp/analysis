import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { fetchUpdateChannel } from "@/lib/api/appStatus";
import { createMockBridge } from "@/lib/bridge/mock";
import { MOCK_UPDATE_CHECKS } from "@/lib/bridge/mock.status";
import { UpdateChannelView, type UpdateChannelViewProps } from "./UpdateChannelPanel";

function render(overrides: Partial<UpdateChannelViewProps>): string {
  const props: UpdateChannelViewProps = {
    loading: false,
    loadError: null,
    browserReason: null,
    channel: "releases",
    check: MOCK_UPDATE_CHECKS.releases,
    checking: false,
    saving: false,
    saveError: null,
    onChange: () => {},
    onCheck: () => {},
    onRetry: () => {},
    ...overrides,
  };
  return renderToStaticMarkup(createElement(MemoryRouter, null, createElement(UpdateChannelView, props)));
}

function radio(html: string, value: string): string {
  const match = html.match(new RegExp(`<input[^>]*value="${value}"[^>]*>`));
  if (!match) throw new Error(`no radio for ${value}`);
  return match[0];
}

describe("mock bridge update channel", () => {
  it("defaults to releases only and reports the newest release as up to date", async () => {
    const bridge = createMockBridge();

    expect(await bridge.get_update_channel!()).toEqual({ channel: "releases" });
    const check = await bridge.check_update!();
    expect(check).toMatchObject({ available: false, status: "up_to_date", channel: "releases", publication_kind: "release" });
    expect(check.checked_at).toBeTruthy();
  });

  it("stores the choice and offers the pre-release on the pre-release channel", async () => {
    const bridge = createMockBridge();

    expect(await bridge.set_update_channel!({ channel: "prereleases" })).toEqual({ ok: true, channel: "prereleases" });
    expect(await bridge.get_update_channel!()).toEqual({ channel: "prereleases" });
    expect(await bridge.check_update!({ force: true })).toMatchObject({
      available: true,
      status: "available",
      channel: "prereleases",
      publication_kind: "pre-release",
      latest_version: "0.30.0-rc.1",
    });
  });

  it("refuses an unknown channel and keeps the choice", async () => {
    const bridge = createMockBridge();

    expect(await bridge.set_update_channel!({ channel: "nightly" })).toMatchObject({ ok: false, channel: "releases" });
    expect(await bridge.get_update_channel!()).toEqual({ channel: "releases" });
  });
});

describe("Update channel in Settings", () => {
  it("shows both choices with releases only selected, the notice, the version and the last check", () => {
    const html = render({});

    expect(html).toContain("Releases only");
    expect(html).toContain("Pre-releases and releases");
    expect(radio(html, "releases")).toContain("checked");
    expect(radio(html, "prereleases")).not.toContain("checked");
    expect(html).toContain("Pre-releases bring features sooner and may be less stable.");
    expect(html).toContain(MOCK_UPDATE_CHECKS.releases.current_version!);
    expect(html).toContain("Up to date");
    expect(html).toContain(new Date(MOCK_UPDATE_CHECKS.releases.checked_at!).toLocaleString());
  });

  it("shows the offered pre-release on the pre-release channel", () => {
    const html = render({ channel: "prereleases", check: MOCK_UPDATE_CHECKS.prereleases });

    expect(radio(html, "prereleases")).toContain("checked");
    expect(html).toContain("Update available");
    expect(html).toContain("0.30.0-rc.1");
    expect(html).toContain("pre-release");
  });

  it("shows a loading state before the channel is known", () => {
    const html = render({ loading: true, channel: null, check: null });

    expect(html).toContain("Loading update channel");
    expect(html).not.toContain('type="radio"');
  });

  it("shows a load error with a retry instead of a default choice", () => {
    const html = render({ loadError: "bridge down", channel: null, check: null });

    expect(html).toContain("Could not load update settings");
    expect(html).toContain("bridge down");
    expect(html).toContain(">retry<");
    expect(html).not.toContain('type="radio"');
  });

  it("keeps the choice usable and says why when the check fails offline", () => {
    const html = render({ check: MOCK_UPDATE_CHECKS.offline });

    expect(html).toContain("Update check failed");
    expect(html).toContain("The app keeps working");
    expect(radio(html, "releases")).not.toContain("disabled");
    expect(html).toContain(new Date(MOCK_UPDATE_CHECKS.offline.checked_at!).toLocaleString());
    expect(html).not.toContain("Up to date");
  });

  it("says when no check has run yet", () => {
    const html = render({ check: { available: false, status: "not_checked", channel: "releases", current_version: "0.29.2", checked_at: null } });

    expect(html).toContain("Not checked yet");
    expect(html).not.toContain("Up to date");
  });

  it("shows a save error next to the choice", () => {
    const html = render({ saveError: "Write blocked: dev mode is using the release data directory." });

    expect(html).toContain("Could not save the update channel");
    expect(html).toContain("Write blocked");
  });

  it("disables the choice in browser preview and explains why", async () => {
    const result = await fetchUpdateChannel();
    expect(result.mode).toBe("browser");

    const html = render({ browserReason: "Running in browser preview.", check: null });

    expect(html).toContain("Running in browser preview.");
    expect(radio(html, "releases")).toContain("disabled");
    expect(radio(html, "prereleases")).toContain("disabled");
  });
});
