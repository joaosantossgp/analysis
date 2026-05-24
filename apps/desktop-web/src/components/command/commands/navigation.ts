import type { NavigateFunction } from "react-router-dom";

import type { Command } from "../CommandRegistry";

/**
 * Static navigation commands (routes). Built once per palette mount with
 * the live navigate function so command activation triggers React Router
 * navigation, not a hard page reload.
 */
export function buildNavigationCommands(navigate: NavigateFunction): Command[] {
  const goto = (path: string) => () => navigate(path);
  return [
    {
      id: "nav:companies",
      group: "navigation",
      glyph: "route",
      label: "Empresas",
      secondary: "/",
      keywords: ["companies", "directory", "diretório", "empresas"],
      run: goto("/"),
    },
    {
      id: "nav:sectors",
      group: "navigation",
      glyph: "route",
      label: "Setores",
      secondary: "/setores",
      keywords: ["sectors", "gics", "setores"],
      run: goto("/setores"),
    },
    {
      id: "nav:database",
      group: "navigation",
      glyph: "route",
      label: "Atualizar base",
      secondary: "/atualizar-base",
      keywords: ["database", "refresh", "update", "ingest", "base"],
      run: goto("/atualizar-base"),
    },
    {
      id: "nav:status",
      group: "navigation",
      glyph: "route",
      label: "Status",
      secondary: "/status",
      keywords: ["diagnostics", "status", "runtime"],
      run: goto("/status"),
    },
    {
      id: "nav:health",
      group: "navigation",
      glyph: "route",
      label: "Bridge health",
      secondary: "/health",
      keywords: ["health", "bridge", "diagnostics"],
      run: goto("/health"),
    },
  ];
}
