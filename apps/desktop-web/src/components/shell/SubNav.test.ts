import { describe, expect, it } from "vitest";

import { subNavFor } from "./SubNav";

describe("Company sub-navigation", () => {
  it("does not expose Excel Mapping as a Company sub-navigation tab", () => {
    expect(subNavFor("/empresas/9512", { cdCvm: "9512" }, null)).not.toContainEqual(
      expect.objectContaining({ label: "Excel Mapping" }),
    );
  });
});
