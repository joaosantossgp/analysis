import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DevDesignSystemPage } from "./DevDesignSystemPage";

describe("DevDesignSystemPage", () => {
  it("gives developers a compact reference for the approved UI system", () => {
    const markup = renderToStaticMarkup(<DevDesignSystemPage />);

    expect(markup).toContain("Design Reference");
    expect(markup).toContain("Principles");
    expect(markup).toContain("Foundations");
    expect(markup).toContain("Assets &amp; Components");
    expect(markup).toContain("Motion");
    expect(markup).toContain("Composition");
    expect(markup).toContain("180 ms");
  });
});
