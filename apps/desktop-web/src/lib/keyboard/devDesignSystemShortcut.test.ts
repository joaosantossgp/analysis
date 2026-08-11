import { describe, expect, it } from "vitest";

import { resolveDevDesignSystemShortcut } from "./devDesignSystemShortcut";

describe("resolveDevDesignSystemShortcut", () => {
  it("opens the design reference only for Ctrl+Alt+D", () => {
    expect(resolveDevDesignSystemShortcut({ key: "d", ctrlKey: true, altKey: true, metaKey: false, shiftKey: false }))
      .toBe("/dev/design-system");
    expect(resolveDevDesignSystemShortcut({ key: "d", ctrlKey: true, altKey: false, metaKey: false, shiftKey: false }))
      .toBeNull();
  });
});
