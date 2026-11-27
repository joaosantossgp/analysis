import { useQuery } from "@tanstack/react-query";

import { DEV_CONTEXT_QUERY_KEY, fetchDevContext } from "@/lib/api/devPanel";

/** Dev context shared by the panel sections; re-read every time the panel opens. */
export function useDevContext() {
  return useQuery({
    queryKey: DEV_CONTEXT_QUERY_KEY,
    queryFn: fetchDevContext,
    staleTime: 0,
    retry: false,
  });
}
