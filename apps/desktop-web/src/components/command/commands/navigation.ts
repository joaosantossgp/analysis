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
      id: "nav:database",
      group: "navigation",
      glyph: "route",
      label: "Database Updates",
      secondary: "/atualizar-base",
      keywords: ["database", "refresh", "update", "ingest", "base", "atualizacao", "atualização"],
      run: goto("/atualizar-base"),
    },
    {
      id: "nav:data-coverage",
      group: "navigation",
      glyph: "route",
      label: "Data Coverage",
      secondary: "/data-coverage",
      keywords: ["coverage", "cobertura", "pendentes", "missing"],
      run: goto("/data-coverage"),
    },
    {
      id: "nav:status",
      group: "navigation",
      glyph: "route",
      label: "System Diagnostics",
      secondary: "/status",
      keywords: ["diagnostics", "status", "runtime", "sistema", "versão"],
      run: goto("/status"),
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
