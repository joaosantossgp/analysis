import { expect, it } from "vitest";
import { createMockBridge } from "./mock";

it("sorts the full mock directory before paginating in both directions", async () => {
  const bridge = createMockBridge();
  const full = await bridge.get_companies!({ page_size: 100 });
  const expected = [...full.items].sort((a, b) => a.cd_cvm - b.cd_cvm);
  for (const direction of ["asc", "desc"] as const) {
    const wanted = direction === "asc" ? expected : [...expected].reverse();
    for (let index = 0; index < wanted.length; index++) {
      const page = await bridge.get_companies!({ sort_by: "cvm", sort_direction: direction, page: index + 1, page_size: 1 });
      expect(page.items.map(item => item.cd_cvm)).toEqual([wanted[index].cd_cvm]);
    }
  }
});
