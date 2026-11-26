import { expect, it } from "vitest";

import { buildActionCommands } from "./actions";

it("labels the folder actions in English", () => {
  const labels = buildActionCommands().map((command) => command.label);
  expect(labels).toContain("Open exports folder");
  expect(labels.some((label) => label.includes("Abrir"))).toBe(false);
});
