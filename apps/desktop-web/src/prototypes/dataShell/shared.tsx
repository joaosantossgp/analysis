// PROTOTYPE (throwaway, dev-only): data shell variants. Do not import from production code paths except the gated slots.
import { useEffect } from "react";
import type { CSSProperties, ReactNode } from "react";

import { Button } from "@/components/ui/Button";

import { setPanelOpen, setState, type DataShellState } from "./store";

/** SIMULATED numbers for the prototype. Nothing here is a real observation. */
export const FIXTURE = {
  total: 438,
  processed: 162,
  pct: 37,
  eta: "~24 min",
  files: { done: 6, total: 10 },
  history: "2022–2026",
  source: "Official CVM · DFP, ITR",
  lastFull: "Aug 2, 2026",
  finishedAt: "Nov 25, 2026 09:42",
  staleDeadline: "ITR 3Q26 deadline passed on Nov 14, 2026",
  failedCount: 12,
  failures: [
    { cdCvm: 4170, name: "OI SA", error: "DFP 2024 rows rejected by validation" },
    { cdCvm: 5258, name: "XP INC", error: "No ITR filed for 3Q26 yet" },
    { cdCvm: 99001, name: "EMPRESA DEMO LTDA", error: "Statement parse error (BPP 2023)" },
  ],
};

export type Tone = "ok" | "warn" | "err" | "info" | "muted";

export const TONE_COLOR: Record<Tone, string> = {
  ok: "var(--color-state-ok)",
  warn: "var(--color-state-warn)",
  err: "var(--color-state-err)",
  info: "var(--color-id-ticker)",
  muted: "var(--color-text-tertiary)",
};

export type StateInfo = {
  glyph: string;
  short: string;
  tone: Tone;
  headline: string;
  detail: string;
  running: boolean;
  empty: boolean;
};

export function stateInfo(state: DataShellState): StateInfo {
  const f = FIXTURE;
  switch (state) {
    case "empty":
      return { glyph: "○", short: "EMPTY", tone: "warn", headline: "Local database is empty", detail: `Download CVM data to load all active companies and their statements for ${f.history}.`, running: false, empty: true };
    case "files":
      return { glyph: "↻", short: `CVM FILES ${f.files.done}/${f.files.total}`, tone: "info", headline: `Downloading CVM files · ${f.files.done} of ${f.files.total}`, detail: "Company list ready. Statements start landing after this step.", running: true, empty: true };
    case "updating":
      return { glyph: "↻", short: `UPDATING ${f.pct}%`, tone: "info", headline: `Updating · ${f.processed} of ${f.total} companies`, detail: `About ${f.eta.replace("~", "")} left · estimate from this run's pace`, running: true, empty: false };
    case "current":
      return { glyph: "●", short: "UP TO DATE", tone: "ok", headline: "Up to date", detail: `Last data update ${f.finishedAt} · ${f.total} companies · ${f.history}`, running: false, empty: false };
    case "stale":
      return { glyph: "▲", short: "STALE", tone: "warn", headline: "New CVM filings may be due", detail: `${f.staleDeadline} · last data update ${f.lastFull}`, running: false, empty: false };
    case "partial":
      return { glyph: "◑", short: `${f.failedCount} FAILED`, tone: "warn", headline: `Completed with ${f.failedCount} failures`, detail: `${f.total - f.failedCount} of ${f.total} companies updated · ${f.finishedAt}`, running: false, empty: false };
    case "failed":
      return { glyph: "!", short: "UPDATE FAILED", tone: "err", headline: "Data update failed", detail: "The CVM server did not respond. The local database was not changed.", running: false, empty: true };
    case "offline":
      return { glyph: "○", short: "EMPTY · OFFLINE", tone: "warn", headline: "Local database is empty", detail: "No internet connection. Connect to download CVM data.", running: false, empty: true };
  }
}

/** The one shared action. Only changes the simulated state. */
export function DataAction({ state, size = "sm", compactRunning = false }: { state: DataShellState; size?: "xs" | "sm"; compactRunning?: boolean }) {
  const info = stateInfo(state);
  if (state === "offline") {
    return (
      <span className="inline-flex items-center gap-2">
        <Button variant="primary" size={size} disabled>Download CVM data</Button>
        <span className="text-xs" style={{ color: "var(--color-state-warn)" }}>Offline — connect to download.</span>
      </span>
    );
  }
  if (info.running) {
    return compactRunning ? (
      <Button variant="ghost" size={size} onClick={() => setPanelOpen(true)}>View progress</Button>
    ) : (
      <Button variant="secondary" size={size} onClick={() => setState("empty")}>Cancel update</Button>
    );
  }
  if (state === "empty" || state === "failed") {
    return <Button variant="primary" size={size} onClick={() => setState("files")}>{state === "failed" ? "Try again" : "Download CVM data"}</Button>;
  }
  if (state === "partial") {
    return <Button variant="secondary" size={size} onClick={() => setState("updating")}>Retry {FIXTURE.failedCount} failed</Button>;
  }
  return <Button variant={state === "stale" ? "primary" : "secondary"} size={size} onClick={() => setState("updating")}>Update data</Button>;
}

export function ProgressBar({ state, height = 4 }: { state: DataShellState; height?: number }) {
  const pct = state === "files" ? 10 + 4.5 * FIXTURE.files.done : state === "updating" ? FIXTURE.pct : null;
  if (pct == null) return null;
  return (
    <div style={{ height, background: "var(--color-surface-4)", borderRadius: 2, overflow: "hidden" }} aria-hidden="true">
      <div style={{ width: `${pct}%`, height: "100%", background: "var(--color-id-ticker)", transition: "width 180ms ease" }} />
    </div>
  );
}

export function SourceLine({ style }: { style?: CSSProperties }) {
  return (
    <p className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)", ...style }}>
      {FIXTURE.source} · {FIXTURE.history} · runs only when you start it, and is logged
    </p>
  );
}

export function FailureList() {
  return (
    <ul className="divide-y" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
      {FIXTURE.failures.map((f) => (
        <li key={f.cdCvm} className="flex items-center justify-between gap-2 py-1.5 text-xs" style={{ borderColor: "var(--color-border-subtle)" }}>
          <span className="min-w-0">
            <span className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>CVM {f.cdCvm} </span>
            <span style={{ color: "var(--color-text-primary)" }}>{f.name}</span>
            <span className="block truncate text-2xs" style={{ color: "var(--color-text-tertiary)" }}>{f.error}</span>
          </span>
          <Button variant="ghost" size="xs" onClick={() => setState("updating")}>Retry</Button>
        </li>
      ))}
      <li className="py-1.5 text-2xs" style={{ color: "var(--color-text-tertiary)" }}>+{FIXTURE.failedCount - FIXTURE.failures.length} more in Data completeness</li>
    </ul>
  );
}

/** Panel body used by A and D (same state rules). */
export function StatePanelBody({ state }: { state: DataShellState }) {
  const info = stateInfo(state);
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-semibold" style={{ color: TONE_COLOR[info.tone] }}>
          <span aria-hidden="true">{info.glyph} </span>
          {info.headline}
        </p>
        <p className="mt-0.5 text-xs" style={{ color: "var(--color-text-secondary)" }}>{info.detail}</p>
      </div>
      <ProgressBar state={state} />
      {state === "updating" ? (
        <dl className="grid grid-cols-3 gap-2 font-mono text-2xs" style={{ color: "var(--color-text-secondary)" }}>
          <div><dt style={{ color: "var(--color-text-tertiary)" }}>PROCESSED</dt><dd>{FIXTURE.processed}/{FIXTURE.total}</dd></div>
          <div><dt style={{ color: "var(--color-text-tertiary)" }}>FAILED</dt><dd>0</dd></div>
          <div><dt style={{ color: "var(--color-text-tertiary)" }}>ETA</dt><dd title="Estimate from this run's pace so far">{FIXTURE.eta}</dd></div>
        </dl>
      ) : null}
      <DataAction state={state} />
      {state === "partial" ? <FailureList /> : null}
      <SourceLine />
    </div>
  );
}

export function useEscapeToClose(open: boolean) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPanelOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
}

export function CloseButton() {
  return (
    <button type="button" aria-label="Close Data panel" onClick={() => setPanelOpen(false)} className="rounded-sm px-1.5 text-sm hover:bg-[var(--color-surface-3)]" style={{ color: "var(--color-text-tertiary)" }}>
      ×
    </button>
  );
}

/** Row badge rules shared by variants that show progress in the Companies list. */
export function queuedRowBadge(cdCvm: number, state: DataShellState): ReactNode | null {
  const done = new Set([9512, 14311]);
  const badge = (text: string, color: string, title: string) => (
    <span title={title} className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono" style={{ borderColor: "var(--color-border-default)", color }}>
      {text}
    </span>
  );
  if (state === "files") return badge("◌ Queued", "var(--color-text-secondary)", "Queued in the running data update. Open the company to download it now.");
  if (state === "updating") {
    if (done.has(cdCvm)) return null;
    if (cdCvm === 14673) return badge("↻ Downloading", "var(--color-id-ticker)", "Downloading now");
    return badge("◌ Queued", "var(--color-text-secondary)", "Queued in the running data update. Open the company to download it now.");
  }
  if (state === "partial" && cdCvm === 4170) return badge("▲ Failed", "var(--color-state-warn)", "DFP 2024 rows rejected by validation. Retry from the Data panel.");
  return null;
}
