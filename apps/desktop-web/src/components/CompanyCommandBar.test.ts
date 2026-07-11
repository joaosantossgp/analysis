import { describe, expect, it } from "vitest";

import * as companyCommandBar from "./CompanyCommandBar";

type InvalidationKeys = (cdCvm: number) => Array<readonly unknown[]>;

function getInvalidationKeys(): InvalidationKeys {
  const keys = Reflect.get(companyCommandBar, "companyDataInvalidationKeys");
  expect(keys).toBeTypeOf("function");
  return keys as InvalidationKeys;
}

describe("Company Command Bar query invalidation", () => {
  it("invalidates financial readiness after the existing company refresh completes", () => {
    expect(getInvalidationKeys()(9512)).toContainEqual([
      "company-financial-readiness",
      9512,
    ]);
  });
});
