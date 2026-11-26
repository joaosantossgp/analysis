export type SettingsNavSection = "overview" | "data" | "sources" | "storage" | "app" | "advanced";

/**
 * The one Settings navigation. The shell sub-navigation and the Settings
 * sidebar both render this list so they can never disagree.
 */
export const SETTINGS_NAV_ITEMS: Array<{
  id: SettingsNavSection;
  label: string;
  to: string;
  activeOn?: string[];
}> = [
  { id: "overview", label: "Overview", to: "/settings" },
  { id: "data", label: "Data", to: "/settings/data" },
  { id: "sources", label: "Sources", to: "/settings/sources", activeOn: ["/settings/imports", "/settings/indicator-sources"] },
  { id: "storage", label: "Storage", to: "/settings/storage" },
  { id: "app", label: "App", to: "/settings/app" },
  { id: "advanced", label: "Advanced", to: "/settings/diagnostics" },
];

/** Retired routes and where their content lives now (ADR 0010: the shell owns data updates). */
export const SETTINGS_REDIRECTS: Record<string, string> = {
  "/settings/updates": "/settings/data",
  "/settings/health": "/settings/data",
  "/settings/coverage": "/settings/data",
  "/atualizar-base": "/settings/data",
  "/company-universe": "/settings/data",
  "/data-coverage": "/settings/data",
  "/status": "/settings/diagnostics",
};
