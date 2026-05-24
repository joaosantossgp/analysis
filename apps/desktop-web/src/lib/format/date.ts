/**
 * Date formatting helpers — CVMAnalytics Terminal UI.
 * pt-BR locale, null-safe.
 */

const EM_DASH = "—";

/**
 * Format an ISO-8601 date string ("2026-05-23" or "2026-05-23T15:04:00Z")
 * as Brazilian short date "23/05/2026". Returns em-dash on null/invalid.
 */
export function formatBRDate(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return d.toLocaleDateString("pt-BR");
}

/**
 * Format an ISO-8601 timestamp as "23/05/2026 15:04" — date + 24h time.
 */
export function formatBRDateTime(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return `${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })}`;
}

/**
 * Format a Unix epoch in seconds (matches Python time.time()) as a
 * Brazilian time HH:MM. Returns em-dash on null/invalid.
 */
export function formatBRTimeFromEpoch(
  epochSeconds: number | null | undefined,
): string {
  if (epochSeconds === null || epochSeconds === undefined) return EM_DASH;
  if (!Number.isFinite(epochSeconds)) return EM_DASH;
  return new Date(epochSeconds * 1000).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
