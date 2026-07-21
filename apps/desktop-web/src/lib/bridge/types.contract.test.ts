import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  createSourceFile,
  isIdentifier,
  isInterfaceDeclaration,
  isMethodSignature,
  isStringLiteral,
  type InterfaceDeclaration,
  ScriptKind,
  ScriptTarget,
} from "typescript";
import { describe, expect, it } from "vitest";

function bridgeApiMethodNames(source: string): string[] {
  const sourceFile = createSourceFile(
    "types.ts",
    source,
    ScriptTarget.Latest,
    true,
    ScriptKind.TS,
  );
  const bridgeApiDeclarations = sourceFile.statements.filter(
    (statement): statement is InterfaceDeclaration =>
      isInterfaceDeclaration(statement) && statement.name.text === "BridgeApi",
  );
  if (bridgeApiDeclarations.length !== 1) {
    throw new Error(
      `Expected exactly one BridgeApi interface, found ${bridgeApiDeclarations.length}`,
    );
  }

  return bridgeApiDeclarations[0].members.flatMap((member) => {
    if (!isMethodSignature(member)) return [];
    if (isIdentifier(member.name) || isStringLiteral(member.name)) {
      return [member.name.text];
    }
    return [];
  });
}

describe("BridgeApi declaration contract", () => {
  it("normalizes valid method signature name forms", () => {
    const names = bridgeApiMethodNames(`
      export interface BridgeApi {
        ping(params?: Record<string, unknown>): Promise<unknown>;
        ping<T>(params: T): Promise<T>;
        "ping"(params?: Record<string, unknown>): Promise<unknown>;
        ping
          (params?: Record<string, unknown>): Promise<unknown>;
      }
    `);
    const counts = new Map<string, number>();
    for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);
    const duplicates = [...counts]
      .filter(([, count]) => count > 1)
      .map(([name]) => name)
      .sort();

    expect(duplicates).toEqual(["ping"]);
    expect(names).toHaveLength(4);
  });

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
