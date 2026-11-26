import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { useRefreshJobInvalidation } from "@/hooks/useRefreshJobInvalidation";
import {
  LOCAL_DATABASE_STATE_KEY,
  retryFailedCompanies,
  useLocalDatabaseState,
  useOnline,
} from "@/lib/api/localDatabase";
import type { LocalDatabaseState } from "@/lib/bridge/types.localDatabase";
import { describeLocalDatabaseState, LOCAL_DATABASE_TONE_COLOR } from "@/lib/localDatabase/describe";
import { OPEN_DATA_PANEL_EVENT } from "@/lib/localDatabase/panel";

import { DataAction } from "./DataAction";

const MAX_LISTED_FAILURES = 5;

/**
 * Top-bar Local database indicator and its Data panel (ADR 0010).
 * Reads local state only; it never starts a data update by itself.
 */
export function DataIndicator() {
  const query = useLocalDatabaseState();
  const online = useOnline();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const state = query.isError
    ? ({ state: "unknown", error: String(query.error) } as LocalDatabaseState)
    : query.data;

  // Refresh every data screen when a run ends, wherever the analyst is.
  const invalidateAll = useRefreshJobInvalidation();
  const running = Boolean(state?.run);
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current && !running) invalidateAll();
    wasRunning.current = running;
  }, [running, invalidateAll]);

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener(OPEN_DATA_PANEL_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_DATA_PANEL_EVENT, onOpen);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Browser preview has no local database to describe.
  if (state === null) return null;

  const d = describeLocalDatabaseState(state, { online });
  const color = LOCAL_DATABASE_TONE_COLOR[d.tone];

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="data-panel"
        aria-label={`Local database: ${d.headline}`}
        onClick={() => setOpen((value) => !value)}
        className="relative inline-flex shrink-0 items-center gap-1 overflow-hidden rounded-sm border px-2 py-0.5 font-mono text-2xs uppercase tracking-wider hover:bg-[var(--color-surface-3)]"
        style={{ borderColor: color, color, background: open ? "var(--color-surface-3)" : undefined }}
      >
        <span aria-hidden="true">{d.glyph}</span>
        {d.short}
      </button>
      {open && state ? (
        <>
          <button
            type="button"
            tabIndex={-1}
            aria-label="Close Data panel"
            onClick={() => setOpen(false)}
            style={{ position: "fixed", inset: 0, background: "transparent", cursor: "default", zIndex: "var(--z-drawer)" as unknown as number }}
          />
          <div
            id="data-panel"
            ref={panelRef}
            role="dialog"
            aria-label="Local database"
            tabIndex={-1}
            style={{
              position: "fixed",
              top: "calc(36px + 32px + 8px)",
              right: 16,
              width: "min(360px, calc(100vw - 32px))",
              maxHeight: "calc(100vh - 116px)",
              overflow: "auto",
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-overlay)",
              zIndex: "var(--z-overlay)" as unknown as number,
            }}
          >
            <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
              <h2 className="text-sm font-semibold" style={{ color: "var(--color-text-primary)" }}>Local database</h2>
              <button
                type="button"
                aria-label="Close Data panel"
                onClick={() => setOpen(false)}
                className="rounded-sm px-1.5 text-sm hover:bg-[var(--color-surface-3)]"
                style={{ color: "var(--color-text-tertiary)" }}
              >
                ×
              </button>
            </div>
            <div className="p-3">
              <DataPanelBody state={state} online={online} />
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}

export function DataPanelBody({ state, online }: { state: LocalDatabaseState; online: boolean }) {
  const d = describeLocalDatabaseState(state, { online });
  const failures = state.state === "partial" || state.state === "failed" ? state.failures : [];
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: (ids?: number[]) => retryFailedCompanies(ids),
    onSettled: () => queryClient.invalidateQueries({ queryKey: LOCAL_DATABASE_STATE_KEY }),
  });
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-semibold" style={{ color: LOCAL_DATABASE_TONE_COLOR[d.tone] }}>
          <span aria-hidden="true">{d.glyph} </span>
          {d.headline}
        </p>
        {d.detail ? (
          <p className="mt-0.5 text-xs" style={{ color: "var(--color-text-secondary)" }}>{d.detail}</p>
        ) : null}
      </div>
      {d.percent != null ? (
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={d.percent}
          style={{ height: 4, background: "var(--color-surface-4)", borderRadius: 2, overflow: "hidden" }}
        >
          <div style={{ width: `${d.percent}%`, height: "100%", background: "var(--color-id-ticker)", transition: "width 180ms ease" }} />
        </div>
      ) : null}
      <DataAction state={state} online={online} context="panel" />
      {failures.length ? (
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-mono text-2xs uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>
            Failed companies
          </h3>
          <Button variant="secondary" size="xs" disabled={!online} loading={retry.isPending} onClick={() => retry.mutate(undefined)}>
            Retry {failures.length} failed
          </Button>
        </div>
      ) : null}
      {retry.error ? (
        <p role="alert" className="text-xs" style={{ color: "var(--color-state-err)" }}>{(retry.error as Error).message}</p>
      ) : null}
      {failures.length ? (
        <ul style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
          {failures.slice(0, MAX_LISTED_FAILURES).map((f) => (
            <li key={f.cd_cvm} className="flex items-start justify-between gap-2 py-1.5 text-xs" style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
              <span className="min-w-0">
                <span className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>CVM {f.cd_cvm} </span>
                <span style={{ color: "var(--color-text-primary)" }}>{f.company_name ?? "Unknown company"}</span>
                <span className="block text-2xs" style={{ color: "var(--color-text-tertiary)" }}>{f.error}</span>
              </span>
              <Button variant="ghost" size="xs" disabled={!online || retry.isPending} onClick={() => retry.mutate([f.cd_cvm])}>
                Retry
              </Button>
            </li>
          ))}
          {failures.length > MAX_LISTED_FAILURES ? (
            <li className="py-1.5 text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
              +{failures.length - MAX_LISTED_FAILURES} more in Data completeness
            </li>
          ) : null}
        </ul>
      ) : null}
      <p className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
        Official CVM · DFP, ITR · Data updates run only when you start them, and are logged.
      </p>
      <a href="#/settings/coverage" className="text-xs" style={{ color: "var(--color-id-link)" }}>
        Data completeness →
      </a>
    </div>
  );
}
