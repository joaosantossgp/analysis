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
      id: "nav:home",
      group: "navigation",
      glyph: "route",
      label: "Home",
      secondary: "/",
      keywords: ["home", "início", "dashboard", "status", "atualizar"],
      run: goto("/"),
    },
    {
      id: "nav:companies",
      group: "navigation",
      glyph: "route",
      label: "Companies",
      secondary: "/empresas",
      keywords: ["companies", "directory", "diretório", "empresas"],
      run: goto("/empresas"),
    },
    {
      id: "nav:sectors",
      group: "navigation",
      glyph: "route",
      label: "Sectors",
      secondary: "/setores",
      keywords: ["sectors", "gics", "setores"],
      run: goto("/setores"),
    },
    {
      id: "nav:coverage",
      group: "navigation",
      glyph: "route",
      label: "Coverage",
      secondary: "/empresas/coverage",
      keywords: ["coverage", "universe", "priorities", "queue"],
      run: goto("/empresas/coverage"),
    },
    {
      id: "nav:data-completeness",
      group: "navigation",
      glyph: "route",
      label: "Data completeness",
      secondary: "/settings/data",
      keywords: ["data completeness", "missing", "gaps", "failed", "retry", "history range", "database"],
      run: goto("/settings/data"),
    },
    {
      id: "nav:sources",
      group: "navigation",
      glyph: "route",
      label: "Sources",
      secondary: "/settings/sources",
      keywords: ["sources", "imports", "ccee", "feeds"],
      run: goto("/settings/sources"),
    },
    {
      id: "nav:app-settings",
      group: "navigation",
      glyph: "route",
      label: "App Settings",
      secondary: "/settings/app",
      keywords: ["app", "runtime", "version", "logs", "paths"],
      run: goto("/settings/app"),
    },
    {
      id: "nav:status",
      group: "navigation",
      glyph: "route",
      label: "System Diagnostics",
      secondary: "/settings/diagnostics",
      keywords: ["diagnostics", "status", "runtime", "sistema", "versão"],
      run: goto("/settings/diagnostics"),
    },
    {
      id: "nav:settings",
      group: "navigation",
      glyph: "route",
      label: "Settings",
      secondary: "/settings",
      keywords: ["settings", "config", "configuration", "paths", "database", "base", "dados"],
      run: goto("/settings"),
    },
  ];
}
