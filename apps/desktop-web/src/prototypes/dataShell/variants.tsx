// PROTOTYPE (throwaway, dev-only): data shell variants. Do not import from production code paths except the gated slots.
import type { FC, ReactNode } from "react";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";

import {
  CloseButton,
  DataAction,
  FailureList,
  FIXTURE,
  ProgressBar,
  queuedRowBadge,
  SourceLine,
  StatePanelBody,
  stateInfo,
  TONE_COLOR,
  useEscapeToClose,
} from "./shared";
import { setPanelOpen, type DataShellState, type VariantKey } from "./store";

type P = { state: DataShellState; panelOpen: boolean };

export type DataShellVariant = {
  key: VariantKey;
  TopBarSlot?: FC<P>;
  StatusSlot?: FC<P>;
  hidesStatusBrandLabel?: boolean;
  Aside?: FC<P>;
  asideWidthPx?: number;
  HomeLead: FC<P>;
  homeLeadBelowHeader?: boolean;
  CompaniesEmpty: FC<P>;
  CompaniesStatusLine?: FC<P>;
  rowBadge?: (cdCvm: number, state: DataShellState) => ReactNode | null;
};

const surfacePanel = {
  background: "var(--color-surface-2)",
  border: "1px solid var(--color-border-default)",
  borderRadius: "var(--radius-md)",
  boxShadow: "var(--shadow-overlay)",
} as const;

function Backdrop() {
  return (
    <button
      type="button"
      tabIndex={-1}
      aria-label="Close Data panel"
      onClick={() => setPanelOpen(false)}
      style={{ position: "fixed", inset: 0, background: "transparent", zIndex: "var(--z-drawer)" as unknown as number, cursor: "default" }}
    />
  );
}

function PanelHeader({ title = "Local database" }: { title?: string }) {
  return (
    <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
      <h2 className="text-sm font-semibold" style={{ color: "var(--color-text-primary)" }}>{title}</h2>
      <CloseButton />
    </div>
  );
}

/** Slim strip shown on Home when the database has data but needs attention. */
function AttentionStrip({ state }: { state: DataShellState }) {
  if (state !== "stale" && state !== "partial") return null;
  const info = stateInfo(state);
  return (
    <div className="flex flex-wrap items-center gap-3 px-3 py-2 text-xs" style={{ background: "var(--color-surface-2)", border: "1px solid var(--color-border-default)", borderRadius: "var(--radius-md)" }}>
      <span style={{ color: TONE_COLOR[info.tone] }}>{info.glyph} {info.headline}</span>
      <span style={{ color: "var(--color-text-tertiary)" }}>{info.detail}</span>
      <span className="ml-auto"><DataAction state={state} size="xs" /></span>
    </div>
  );
}

function CompaniesEmptyBanner({ state }: P) {
  const offline = state === "offline";
  return (
    <StateBanner
      variant="empty"
      title="No companies"
      message={offline ? "The local database is empty and there is no internet connection." : `The local database is empty. Download CVM data to list every active company; statements for ${FIXTURE.history} follow company by company.`}
    >
      <div className="mt-3 space-y-2">
        <DataAction state={state} />
        <SourceLine />
      </div>
    </StateBanner>
  );
}

function PhaseStatusLine({ state }: P) {
  if (state === "partial") {
    return (
      <p className="mb-2 text-xs" style={{ color: "var(--color-state-warn)" }}>
        ▲ Last data update finished with {FIXTURE.failedCount} failures · failed rows are marked below
      </p>
    );
  }
  return (
    <div className="mb-2 flex items-center gap-3 text-xs" style={{ color: "var(--color-text-secondary)" }}>
      <span style={{ color: "var(--color-id-ticker)" }}>↻</span>
      {state === "files" ? (
        <span>Data update running · Step 1 of 2 · downloading CVM files ({FIXTURE.files.done} of {FIXTURE.files.total}) · statements start landing after this step</span>
      ) : (
        <span>Data update running · {FIXTURE.processed} of {FIXTURE.total} companies processed · rows update as companies finish</span>
      )}
      <button type="button" className="ml-auto text-xs underline" style={{ color: "var(--color-id-link)" }}>Saved first</button>
    </div>
  );
}

/* ───────────── A · Status strip native ───────────── */

const A: DataShellVariant = {
  key: "A",
  hidesStatusBrandLabel: true,
  StatusSlot: ({ state, panelOpen }) => {
    const info = stateInfo(state);
    useEscapeToClose(panelOpen);
    const extra = state === "current" ? ` · ${FIXTURE.finishedAt.toUpperCase()}` : state === "updating" ? ` · ETA ${FIXTURE.eta}` : "";
    return (
      <>
        <button
          type="button"
          aria-haspopup="dialog"
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen(!panelOpen)}
          className="ml-auto inline-flex h-full items-center gap-1.5 px-2 font-mono text-2xs uppercase tracking-wider hover:bg-[var(--color-surface-3)]"
          style={{ color: TONE_COLOR[info.tone] }}
        >
          <span aria-hidden="true">{info.glyph}</span> LOCAL DATABASE · {info.short}
          <span style={{ color: "var(--color-text-tertiary)" }}>{extra}</span>
        </button>
        {panelOpen ? (
          <>
            <Backdrop />
            <div role="dialog" aria-label="Local database" style={{ ...surfacePanel, position: "fixed", right: 16, bottom: 32, width: "min(360px, calc(100vw - 32px))", maxHeight: "calc(100vh - 116px)", overflow: "auto", zIndex: "var(--z-overlay)" as unknown as number }}>
              <PanelHeader />
              <div className="p-3"><StatePanelBody state={state} /></div>
              <div className="px-3 py-2 font-mono text-2xs" style={{ borderTop: "1px solid var(--color-border-subtle)", color: "var(--color-text-tertiary)" }}>BRIDGE · READY · ENV · DEV</div>
            </div>
          </>
        ) : null}
      </>
    );
  },
  HomeLead: ({ state }) => {
    const info = stateInfo(state);
    if (!info.empty) return <AttentionStrip state={state} />;
    return (
      <div className="flex flex-wrap items-center gap-3 px-4 py-2.5" style={{ background: "var(--color-surface-2)", border: "1px solid var(--color-border-default)", borderRadius: "var(--radius-md)" }}>
        <span className="font-mono text-md" style={{ color: TONE_COLOR[info.tone] }} aria-hidden="true">{info.glyph}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold" style={{ color: "var(--color-text-primary)" }}>{info.running ? info.headline : info.headline}</p>
          <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>{info.detail}</p>
          {info.running ? <div className="mt-1.5 max-w-md"><ProgressBar state={state} /></div> : null}
        </div>
        <p className="text-right font-mono text-2xs" style={{ color: "var(--color-text-secondary)" }}>{FIXTURE.source}<br />{FIXTURE.history}</p>
        <DataAction state={state} compactRunning />
      </div>
    );
  },
  CompaniesEmpty: CompaniesEmptyBanner,
  rowBadge: queuedRowBadge,
};

/* ───────────── B · Top bar pill + side drawer ───────────── */

function BDrawerBody({ state }: P) {
  const info = stateInfo(state);
  return (
    <div className="flex h-full flex-col">
      <PanelHeader />
      <div className="flex-1 space-y-4 overflow-auto p-3">
        <div>
          <p className="text-sm font-semibold" style={{ color: TONE_COLOR[info.tone] }}>{info.glyph} {info.headline}</p>
          <p className="mt-0.5 text-xs" style={{ color: "var(--color-text-secondary)" }}>{info.detail}</p>
        </div>
        <ProgressBar state={state} height={6} />
        <DataAction state={state} />
        <dl className="space-y-1.5 text-xs">
          {[
            ["Last data update", info.empty ? "Never" : state === "stale" ? FIXTURE.lastFull : FIXTURE.finishedAt],
            ["Companies", info.empty ? "—" : String(FIXTURE.total)],
            ["History range", FIXTURE.history],
            ["Source", FIXTURE.source],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3">
              <dt style={{ color: "var(--color-text-tertiary)" }}>{k}</dt>
              <dd className="font-mono" style={{ color: "var(--color-text-secondary)" }}>{v}</dd>
            </div>
          ))}
        </dl>
        {state === "partial" ? (
          <section>
            <h3 className="mb-1 font-mono text-2xs uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>Failed companies</h3>
            <FailureList />
          </section>
        ) : null}
      </div>
      <div className="px-3 py-2 text-xs" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
        <a href="#/settings/coverage" style={{ color: "var(--color-id-link)" }}>Open Data completeness →</a>
      </div>
    </div>
  );
}

const B: DataShellVariant = {
  key: "B",
  asideWidthPx: 320,
  TopBarSlot: ({ state, panelOpen }) => {
    const info = stateInfo(state);
    const label = state === "updating" ? `DATA · ${FIXTURE.pct}%` : state === "files" ? "DATA · FILES 6/10" : `DATA · ${info.short}`;
    return (
      <button
        type="button"
        aria-expanded={panelOpen}
        aria-controls="data-panel"
        onClick={() => setPanelOpen(!panelOpen)}
        className="relative inline-flex shrink-0 items-center gap-1 overflow-hidden rounded-sm border px-2 py-0.5 font-mono text-2xs uppercase tracking-wider hover:bg-[var(--color-surface-3)]"
        style={{ borderColor: TONE_COLOR[info.tone], color: TONE_COLOR[info.tone], background: panelOpen ? "var(--color-surface-3)" : undefined }}
      >
        <span aria-hidden="true">{info.glyph}</span>
        {label}
        {info.running ? <span style={{ position: "absolute", left: 0, bottom: 0, height: 2, width: `${state === "updating" ? FIXTURE.pct : 37}%`, background: "var(--color-id-ticker)" }} /> : null}
      </button>
    );
  },
  Aside: ({ state, panelOpen }) => {
    useEscapeToClose(panelOpen);
    if (!panelOpen) return null;
    const wide = window.innerWidth >= 1024;
    return (
      <aside
        id="data-panel"
        aria-label="Local database"
        style={{
          gridArea: wide ? "aside" : undefined,
          position: wide ? "relative" : "fixed",
          top: wide ? undefined : 68,
          bottom: wide ? undefined : 24,
          right: wide ? undefined : 0,
          width: 320,
          minHeight: 0,
          background: "var(--color-surface-2)",
          borderLeft: "1px solid var(--color-border-strong)",
          boxShadow: wide ? undefined : "var(--shadow-drawer)",
          zIndex: wide ? undefined : ("var(--z-drawer)" as unknown as number),
        }}
      >
        <BDrawerBody state={state} panelOpen={panelOpen} />
      </aside>
    );
  },
  HomeLead: ({ state }) => {
    const info = stateInfo(state);
    if (!info.empty) return <AttentionStrip state={state} />;
    return (
      <div className="mx-auto max-w-2xl space-y-3 p-5" style={{ background: "var(--color-surface-2)", border: "1px solid var(--color-border-subtle)", borderRadius: "var(--radius-md)" }}>
        <p className="font-mono text-2xs uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>Local database</p>
        <h3 className="text-lg font-semibold" style={{ color: "var(--color-text-primary)" }}>{state === "files" ? "Downloading CVM data" : info.headline}</h3>
        <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
          {state === "empty" ? "Download official CVM filings for every active company. The company list appears in seconds; statements fill in as each company is processed." : info.detail}
        </p>
        {info.running ? <ProgressBar state={state} height={6} /> : null}
        <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-2xs" style={{ color: "var(--color-text-secondary)" }}>
          <span>SOURCE {FIXTURE.source.toUpperCase()}</span>
          <span>HISTORY {FIXTURE.history}</span>
          <span>SCOPE ALL ACTIVE COMPANIES</span>
        </div>
        <div className="flex items-center gap-3">
          <DataAction state={state} compactRunning />
          <a href="#/empresas" className="text-xs" style={{ color: "var(--color-id-link)" }}>Open Companies</a>
        </div>
      </div>
    );
  },
  CompaniesEmpty: CompaniesEmptyBanner,
  CompaniesStatusLine: ({ state }) =>
    state === "partial" ? null : (
      <p className="mb-2 font-mono text-xs" style={{ color: "var(--color-text-tertiary)" }}>
        Data update running · {state === "files" ? "downloading CVM files" : `${FIXTURE.processed} of ${FIXTURE.total} companies processed`} · rows update as companies finish
      </p>
    ),
  rowBadge: queuedRowBadge,
};

/* ───────────── C · Inline-first ───────────── */

const C: DataShellVariant = {
  key: "C",
  TopBarSlot: ({ state, panelOpen }) => {
    const info = stateInfo(state);
    useEscapeToClose(panelOpen);
    const attention = ["empty", "stale", "partial", "failed", "offline"].includes(state);
    return (
      <>
        <button
          type="button"
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen(!panelOpen)}
          className="inline-flex h-[22px] shrink-0 items-center gap-1.5 rounded-sm border px-1.5 font-mono text-2xs uppercase tracking-wider"
          style={{ borderColor: attention ? TONE_COLOR[info.tone] : "transparent", color: attention ? TONE_COLOR[info.tone] : "var(--color-text-tertiary)" }}
        >
          <span aria-hidden="true" style={{ color: TONE_COLOR[info.tone] }}>{info.glyph}</span>
          DATA{info.running || attention ? ` · ${info.short}` : ""}
        </button>
        {panelOpen ? (
          <>
            <Backdrop />
            <div role="dialog" aria-label="Data update summary" style={{ ...surfacePanel, position: "fixed", top: 42, right: 16, width: "min(340px, calc(100vw - 32px))", padding: 12, zIndex: "var(--z-overlay)" as unknown as number }}>
              <p className="text-sm font-semibold" style={{ color: TONE_COLOR[info.tone] }}>{info.glyph} {info.headline}</p>
              <p className="mt-0.5 text-xs" style={{ color: "var(--color-text-secondary)" }}>{info.detail}</p>
              <div className="my-2"><ProgressBar state={state} /></div>
              <div className="flex items-center gap-3">
                <DataAction state={state} size="xs" />
                {state === "partial" ? <a href="#/empresas" className="text-xs" style={{ color: "var(--color-id-link)" }}>Show failed companies</a> : null}
              </div>
            </div>
          </>
        ) : null}
      </>
    );
  },
  HomeLead: ({ state }) => {
    const info = stateInfo(state);
    if (!info.empty) return <AttentionStrip state={state} />;
    return (
      <div className="mx-auto mt-10 max-w-xl space-y-3 text-center">
        <p className="font-mono text-2xs uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>Local database · empty</p>
        <h3 className="text-2xl font-semibold" style={{ color: "var(--color-text-primary)" }}>
          {state === "files" ? "Getting CVM data" : state === "failed" ? "The download didn't finish" : "No CVM data on this computer yet"}
        </h3>
        <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
          {state === "files" ? "The company list is ready. Watch statements arrive in Companies." : info.detail}
        </p>
        {info.running ? <div className="mx-auto max-w-sm"><ProgressBar state={state} height={6} /></div> : null}
        <p className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>{FIXTURE.source} · {FIXTURE.history}</p>
        <div className="flex justify-center gap-3">
          {info.running ? <a href="#/empresas" className="text-sm" style={{ color: "var(--color-id-link)" }}>Open Companies to watch progress →</a> : <DataAction state={state} />}
        </div>
      </div>
    );
  },
  CompaniesEmpty: CompaniesEmptyBanner,
  CompaniesStatusLine: PhaseStatusLine,
  rowBadge: queuedRowBadge,
};

/* ───────────── D · A+ hybrid ───────────── */

const D: DataShellVariant = {
  key: "D",
  TopBarSlot: ({ state, panelOpen }) => {
    const info = stateInfo(state);
    useEscapeToClose(panelOpen);
    return (
      <>
        <button
          type="button"
          aria-haspopup="dialog"
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen(!panelOpen)}
          className="inline-flex shrink-0 items-center gap-1 rounded-sm border px-2 py-0.5 font-mono text-2xs uppercase tracking-wider hover:bg-[var(--color-surface-3)]"
          style={{ borderColor: TONE_COLOR[info.tone], color: TONE_COLOR[info.tone], background: panelOpen ? "var(--color-surface-3)" : undefined }}
        >
          <span aria-hidden="true">{info.glyph}</span> {info.short}
        </button>
        {panelOpen ? (
          <>
            <Backdrop />
            <div role="dialog" aria-label="Local database" style={{ ...surfacePanel, position: "fixed", top: "calc(36px + 32px + 8px)", right: 16, width: "min(360px, calc(100vw - 32px))", maxHeight: "calc(100vh - 116px)", overflow: "auto", zIndex: "var(--z-overlay)" as unknown as number }}>
              <PanelHeader />
              <div className="p-3"><StatePanelBody state={state} /></div>
              <div className="px-3 py-2 text-xs" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
                <a href="#/settings/coverage" style={{ color: "var(--color-id-link)" }}>Data completeness →</a>
              </div>
            </div>
          </>
        ) : null}
      </>
    );
  },
  HomeLead: ({ state }) => {
    const info = stateInfo(state);
    if (!info.empty) return <AttentionStrip state={state} />;
    return (
      <div className="max-w-2xl space-y-2.5 p-4" style={{ background: "var(--color-surface-2)", border: "1px solid var(--color-border-subtle)", borderRadius: "var(--radius-md)" }}>
        <p className="text-sm font-semibold" style={{ color: TONE_COLOR[info.tone] }}>{info.glyph} {state === "files" ? info.headline : info.headline}</p>
        <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>{info.detail}</p>
        {info.running ? <ProgressBar state={state} /> : null}
        <SourceLine />
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <DataAction state={state} compactRunning />
          <span className="mx-1 h-4 w-px" style={{ background: "var(--color-border-default)" }} aria-hidden="true" />
          <Button variant="ghost" size="xs">Load recommended layout</Button>
          <Button variant="ghost" size="xs">Choose widgets</Button>
        </div>
      </div>
    );
  },
  CompaniesEmpty: CompaniesEmptyBanner,
  CompaniesStatusLine: PhaseStatusLine,
  rowBadge: queuedRowBadge,
};

/* ───────────── E · Chosen (Q24): C hero below the workspace header, A+ header ───────────── */

const E: DataShellVariant = {
  key: "E",
  TopBarSlot: D.TopBarSlot,
  HomeLead: C.HomeLead,
  homeLeadBelowHeader: true,
  CompaniesEmpty: CompaniesEmptyBanner,
  CompaniesStatusLine: PhaseStatusLine,
  rowBadge: queuedRowBadge,
};

export const VARIANTS: Record<VariantKey, DataShellVariant> = { A, B, C, D, E };
