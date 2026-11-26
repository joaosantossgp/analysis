import { useQueryClient } from "@tanstack/react-query";

const REFRESH_JOB_QUERY_KEYS: Array<readonly unknown[]> = [
  ["base-health"],
  ["companies"],
  ["company-filters"],
  ["db-diagnostics"],
  ["command-palette", "companies-index"],
  ["local-database-state"],
  ["sectors"],
  ["sector-detail"],
  ["sub-sector-detail"],
  ["company-info"],
  ["company-years"],
  ["company-statement-years"],
  ["company-kpis"],
  ["company-statement"],
  ["company-refresh-status"],
  ["onboarding-state"],
  ["app-status"],
  ["data-coverage"],
  ["data-update-settings"],
  ["company-universe-selection"],
];

export function useRefreshJobInvalidation() {
  const queryClient = useQueryClient();
  return function invalidateAll() {
    for (const queryKey of REFRESH_JOB_QUERY_KEYS) {
      void queryClient.invalidateQueries({ queryKey });
    }
  };
}
