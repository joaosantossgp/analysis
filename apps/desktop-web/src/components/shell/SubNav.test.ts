import { describe, expect, it } from "vitest";

import { subNavFor } from "./SubNav";

describe("Company sub-navigation", () => {
  it("does not expose Excel Mapping as a Company sub-navigation tab", () => {
    expect(subNavFor("/empresas/9512", { cdCvm: "9512" }, null)).not.toContainEqual(
      expect.objectContaining({ label: "Excel Mapping" }),
    );
  });
});

it("keeps Companies navigation available before selecting a universe", () => {
  const tabs = subNavFor("/empresas/coverage", {}, null);
  expect(tabs).toContainEqual(expect.objectContaining({to: "/empresas", label: "Directory"}));
  expect(tabs).toContainEqual(expect.objectContaining({to: "/empresas/coverage", label: "Coverage"}));
  expect(tabs).not.toContainEqual(expect.objectContaining({to: "/empresas/coverage/demonstrativos"}));
});
it("offers the existing queue and capacity under Companies", () => {
  const tabs = subNavFor("/empresas/coverage/work-queue", {}, "saved");
  expect(tabs).toContainEqual(expect.objectContaining({to: "/empresas/coverage/work-queue"}));
  expect(tabs).toContainEqual(expect.objectContaining({to: "/empresas/coverage/capacity"}));
});
