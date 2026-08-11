import { describe, expect, it } from "vitest";

import { isExcelMappingWindow } from "./windowMode";

describe("Excel Mapping window mode", () => {
  it("identifies the native Excel Mapping window query", () => {
    expect(isExcelMappingWindow("?window=excel-mapping")).toBe(true);
    expect(isExcelMappingWindow("")).toBe(false);
  });
});
