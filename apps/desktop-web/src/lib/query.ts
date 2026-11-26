import { QueryClient } from "@tanstack/react-query";

/**
 * Shared QueryClient. Defaults tuned for a local-first desktop app: data
 * comes from a local SQLite-backed bridge with sub-second latency, so
 * aggressive caching and infrequent revalidation are appropriate.
 *
 * networkMode "always": bridge calls never touch the browser network, so the
 * window `offline` event must not pause them (#575). Bridge methods that reach
 * external sources report their own failures.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 300_000,
      retry: 1,
      refetchOnWindowFocus: false,
      networkMode: "always",
    },
    mutations: {
      networkMode: "always",
    },
  },
});
