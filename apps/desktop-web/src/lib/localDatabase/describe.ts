import type { LocalDatabaseState } from "../bridge/types.localDatabase";

export type LocalDatabaseTone = "ok" | "warn" | "err" | "info" | "muted";

export type LocalDatabaseDescription = {
  glyph: string;
  /** Uppercase label for the top-bar pill. */
  short: string;
  tone: LocalDatabaseTone;
  headline: string;
  detail: string;
  /** 0-100 while a data update runs, otherwise null. */
  percent: number | null;
  offline: boolean;
};

export const LOCAL_DATABASE_TONE_COLOR: Record<LocalDatabaseTone, string> = {
  ok: "var(--color-state-ok)",
  warn: "var(--color-state-warn)",
  err: "var(--color-state-err)",
  info: "var(--color-id-ticker)",
  muted: "var(--color-text-tertiary)",
};

function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  // Date-only values (deadlines) are calendar dates, not instants.
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function formatEta(seconds: number | null): string | null {
  if (seconds == null) return null;
  if (seconds < 60) return "Under a minute left";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `About ${minutes} min left, from this run's pace`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `About ${hours} h${rest ? ` ${rest} min` : ""} left, from this run's pace`;
}

export function describeLocalDatabaseState(
  state: LocalDatabaseState | null | undefined,
  { online }: { online: boolean },
): LocalDatabaseDescription {
  const base = describe(state);
  if (online || !state) return { ...base, offline: false };
  return {
    ...base,
    short: `${base.short} · OFFLINE`,
    detail: base.detail ? `${base.detail} · No internet connection.` : "No internet connection.",
    offline: true,
  };
}

function describe(state: LocalDatabaseState | null | undefined): Omit<LocalDatabaseDescription, "offline"> {
  if (!state) {
    return { glyph: "◌", short: "CHECKING", tone: "muted", headline: "Checking local database…", detail: "", percent: null };
  }
  const lastUpdate = formatDate(state.last_full_update_at);
  const run = state.run;
  switch (state.state) {
    case "empty":
      return {
        glyph: "○",
        short: "EMPTY",
        tone: "warn",
        headline: "Local database is empty",
        detail: "Download CVM data to load every active company and its statements.",
        percent: null,
      };
    case "files": {
      const done = run?.files_done ?? null;
      const total = run?.files_total ?? null;
      if (done == null || !total) {
        return { glyph: "↻", short: "STARTING", tone: "info", headline: "Starting data update", detail: "Getting the CVM company list.", percent: 2 };
      }
      return {
        glyph: "↻",
        short: `CVM FILES ${done}/${total}`,
        tone: "info",
        headline: `Downloading CVM files · ${done} of ${total}`,
        detail: "The company list is ready. Statements start arriving after this step.",
        percent: Math.round((done / total) * 10),
      };
    }
    case "updating": {
      const processed = run?.processed ?? 0;
      const queued = run?.queued ?? 0;
      const percent = queued ? Math.round((processed / queued) * 100) : 0;
      return {
        glyph: "↻",
        short: `UPDATING ${percent}%`,
        tone: "info",
        headline: `Updating · ${processed} of ${queued} companies`,
        detail: formatEta(run?.eta_seconds ?? null) ?? "Estimating time left…",
        percent,
      };
    }
    case "current":
      return {
        glyph: "●",
        short: "UP TO DATE",
        tone: "ok",
        headline: "Up to date",
        detail: lastUpdate ? `Last data update ${lastUpdate}` : "",
        percent: null,
      };
    case "stale": {
      const reason = state.stale_reason;
      const due = formatDate(reason?.due);
      const detail =
        reason?.label && due
          ? `${reason.label} deadline passed on ${due}${lastUpdate ? ` · last data update ${lastUpdate}` : ""}`
          : "No full data update has been recorded yet.";
      return { glyph: "▲", short: "STALE", tone: "warn", headline: "New CVM filings may be due", detail, percent: null };
    }
    case "partial": {
      const last = state.last_run;
      const failures = last?.failures ?? state.failures.length;
      const queued = last?.queued ?? 0;
      const finished = formatDate(last?.finished_at);
      return {
        glyph: "◑",
        short: `${failures} FAILED`,
        tone: "warn",
        headline: `Completed with ${failures} failures`,
        detail: `${Math.max(0, queued - failures)} of ${queued} companies updated${finished ? ` · ${finished}` : ""}`,
        percent: null,
      };
    }
    case "failed":
      return {
        glyph: "!",
        short: "UPDATE FAILED",
        tone: "err",
        headline: "Data update failed",
        detail: state.last_run?.error || "The last data update did not finish.",
        percent: null,
      };
    default: {
      // The bridge answers { state: "unknown", error } when it cannot read local files.
      const error = (state as { error?: string }).error;
      return {
        glyph: "!",
        short: "STATE UNAVAILABLE",
        tone: "err",
        headline: "Local database state unavailable",
        detail: error || "The app could not read the local database.",
        percent: null,
      };
    }
  }
}
