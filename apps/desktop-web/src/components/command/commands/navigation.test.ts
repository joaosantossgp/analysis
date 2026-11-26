import { describe, expect, it, vi } from "vitest";

import { buildNavigationCommands } from "./navigation";

describe("navigation commands", () => {
  it("opens Data completeness instead of the retired Data Updates page", () => {
    const navigate = vi.fn();
    const commands = buildNavigationCommands(navigate);

    expect(commands.map((command) => command.label)).not.toContain("Data Updates");
    expect(commands.some((command) => command.secondary === "/settings/updates")).toBe(false);

    const command = commands.find((item) => item.label === "Data completeness");
    expect(command?.secondary).toBe("/settings/data");
    command?.run();
    expect(navigate).toHaveBeenCalledWith("/settings/data");
  });
});
