import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function bridgeApiMethodNames(source: string): string[] {
  const marker = "export interface BridgeApi {";
  const start = source.indexOf(marker);
  if (start < 0) throw new Error("BridgeApi interface marker not found");

  const names: string[] = [];
  for (const line of source.slice(start + marker.length).split(/\r?\n/)) {
    if (line.trim() === "}" && !/^\s/.test(line)) break;
    const match = /^\s+([A-Za-z_$][\w$]*)\s*\(/.exec(line);
    if (match) names.push(match[1]);
  }
  return names;
}

describe("BridgeApi declaration contract", () => {
  it("declares every method name exactly once", () => {
    const path = fileURLToPath(new URL("./types.ts", import.meta.url));
    const names = bridgeApiMethodNames(readFileSync(path, "utf8"));
    expect(names.length).toBeGreaterThanOrEqual(100);
    expect(names).toEqual(expect.arrayContaining([
      "ping",
      "get_companies",
      "export_company_excel",
    ]));
    const counts = new Map<string, number>();
    for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);

    const duplicates = [...counts]
      .filter(([, count]) => count > 1)
      .map(([name]) => name)
      .sort();
    expect(duplicates).toEqual([]);
  });
});
