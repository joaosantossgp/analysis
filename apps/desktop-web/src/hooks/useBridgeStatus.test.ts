import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __getBridgeStatusSnapshotForTesting,
  __resetBridgeStatusForTesting,
  triggerBridgeCheck,
} from "./useBridgeStatus";

describe("useBridgeStatus probe", () => {
  afterEach(() => {
    __resetBridgeStatusForTesting();
    vi.unstubAllGlobals();
  });

  it("falls back to app status when the desktop bridge does not expose ping", async () => {
    vi.stubGlobal("window", {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      setInterval: vi.fn(),
      clearInterval: vi.fn(),
      pywebview: {
        api: {
          get_app_status: vi.fn().mockResolvedValue({
            runtime: { bridge_status: "ready" },
          }),
        },
      },
    });

    await triggerBridgeCheck();

    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({
      kind: "ready",
      mode: "desktop",
      pingTs: null,
    });
  });
});
