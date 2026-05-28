/**
 * Date formatting helpers — CVMAnalytics Terminal UI.
 * en-US locale, null-safe.
 */

const EM_DASH = "—";

export function formatBRDate(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return d.toLocaleDateString("en-US");
}

export function formatBRDateTime(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return `${d.toLocaleDateString("en-US")} ${d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })}`;
}

export function formatBRTimeFromEpoch(
  epochSeconds: number | null | undefined,
): string {
  if (epochSeconds === null || epochSeconds === undefined) return EM_DASH;
  if (!Number.isFinite(epochSeconds)) return EM_DASH;
  return new Date(epochSeconds * 1000).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
