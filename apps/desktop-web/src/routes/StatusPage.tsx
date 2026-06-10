import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  fetchAppStatus,
  openStatusPath,
  type StatusPathKind,
  triggerApplyUpdate,
  fetchUpdateProgress,
} from "@/lib/api/appStatus";
import { PageHeader as UnifiedPageHeader } from "@/components/PageHeader";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type {
  AppStatusPayload,
  DatabaseDiagnostics,
  DiagnosticLogEntry,
  DiagnosticsSummary,
  LocalPathInfo,
  LockStatusPayload,
  UpdateStatus,
  UpdateProgressStatus,
} from "@/lib/bridge/types";

const PATH_ORDER: StatusPathKind[] = ["data", "database", "output", "logs", "cache"];

export function StatusPage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [forceCheckCount, setForceCheckCount] = useState(0);
  const [copiedKind, setCopiedKind] = useState<string | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const statusQuery = useQuery({
    queryKey: ["app-status", forceCheckCount],
    queryFn: () => fetchAppStatus({ forceUpdateCheck: forceCheckCount > 0 }),
    enabled: bridgeReady,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const openMutation = useMutation({
    mutationFn: openStatusPath,
  });

  const result = statusQuery.data;
  const status = result?.status ?? null;
  const browserReason = result?.mode === "browser" ? result.reason : null;
  const loading = !bridgeReady || (statusQuery.isLoading && !status);

  async function copyPath(kind: string, path: string) {
    setCopyError(null);
    try {
      await navigator.clipboard.writeText(path);
      setCopiedKind(kind);
    } catch {
      setCopyError("Could not copy path. Select the path text manually.");
    }
  }

  return (
    <section className="space-y-5">
      <PageHeader
        loading={loading}
        status={status}
        checking={statusQuery.isFetching}
        onCheckUpdates={() => setForceCheckCount((value) => value + 1)}
      />

      {browserReason ? <BrowserFallback reason={browserReason} /> : null}

      {statusQuery.error ? (
        <Alert tone="error" title="Status unavailable">
          {statusQuery.error instanceof Error
            ? statusQuery.error.message
            : String(statusQuery.error)}
        </Alert>
      ) : null}

      {loading || !status ? (
        <LoadingState />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
            <RuntimeCard status={status} />
            <LocalPathsCard
              paths={status.paths}
              desktopMode={result?.mode === "desktop"}
              openingKind={openMutation.isPending ? (openMutation.variables ?? null) : null}
              openError={openMutation.error}
              copiedKind={copiedKind}
              copyError={copyError}
              onOpen={(kind) => openMutation.mutate(kind)}
              onCopy={copyPath}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <DatabaseCard database={status.database} />
            <UpdateCard
              update={status.update}
              checking={statusQuery.isFetching}
              onCheckUpdates={() => setForceCheckCount((value) => value + 1)}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <DiagnosticsCard diagnostics={status.diagnostics} />
            <RecentDiagnostics entries={status.recent} />
          </div>
        </>
      )}
    </section>
  );
}

function PageHeader({
  loading,
  status,
  checking,
  onCheckUpdates,
}: {
  loading: boolean;
  status: AppStatusPayload | null;
  checking: boolean;
  onCheckUpdates: () => void;
}) {
  const runtime = status?.runtime;
  return (
    <header className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <UnifiedPageHeader
        title="Status"
        subtitle="Runtime, local data, database, software updater, and diagnostics for the default Vite desktop mode. Software update is separate from Database Updates."
        actions={
          <div className="flex flex-col items-end gap-2 text-right">
            <StatusPill tone={runtime?.bridge_status === "ready" ? "good" : "warn"}>
              {loading ? "Connecting bridge" : `Bridge ${runtime?.bridge_status ?? "unknown"}`}
            </StatusPill>
            <button
              type="button"
              disabled={checking}
              onClick={onCheckUpdates}
              className="rounded-md border border-cyan-700/70 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-100 hover:bg-cyan-500/15 disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-600 font-mono"
            >
              {checking ? "Checking releases..." : "Check software update"}
            </button>
          </div>
        }
      />
    </header>
  );
}

function RuntimeCard({ status }: { status: AppStatusPayload }) {
  const runtime = status.runtime;
  const warningCount = status.diagnostics.warnings.length;
  const errorCount = status.diagnostics.errors.length;
  const mode = runtime.runtime_mode;
  const modeLabel =
    mode === "vite-dev-release-data"
      ? "vite dev (release data)"
      : mode === "vite-dev"
        ? "vite dev"
        : mode === "vite"
          ? "vite (default)"
          : mode === "mock"
            ? "mock (fixture)"
            : mode;
  const showReleaseDataWarning = runtime.using_release_data_dir === true && !runtime.frozen;
  return (
    <Card
      title="Runtime"
      eyebrow="Vite shell"
      tone={runtime.bridge_status === "ready" && errorCount === 0 ? "good" : "warn"}
    >
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <Field label="Version" value={runtime.version} mono />
        {runtime.build_commit && (
          <Field label="Build commit" value={runtime.build_commit} mono />
        )}
        {runtime.build_time && (
          <Field label="Build time" value={formatDateTime(runtime.build_time)} />
        )}
        <Field label="Mode" value={modeLabel} />
        <Field label="Bridge" value={runtime.bridge_status} tone={runtime.bridge_status === "ready" ? "good" : "warn"} />
        <Field label="Packaged" value={runtime.frozen ? "yes" : "no"} />
        <Field label="Shell" value={runtime.desktop_shell ?? "unknown"} />
        <Field label="Local-first" value={runtime.local_first ? "yes" : "unknown"} tone="good" />
        {runtime.write_mode && (
          <Field
            label="Write mode"
            value={runtime.write_mode}
            tone={runtime.write_mode === "read-only" ? "warn" : "neutral"}
          />
        )}
        {runtime.lock_status && (
          <Field
            label="Lock"
            value={lockStatusLabel(runtime.lock_status)}
            tone={lockStatusTone(runtime.lock_status)}
          />
        )}
      </dl>
      {showReleaseDataWarning && (
        <p className="mt-4 rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
          Dev mode is using the release data directory. Destructive actions affect real user data.
        </p>
      )}
      <p className="mt-4 border-t border-zinc-800 pt-3 text-xs text-zinc-500">
        Diagnostics: {errorCount} error{errorCount === 1 ? "" : "s"} · {warningCount} warning
        {warningCount === 1 ? "" : "s"}.
      </p>
      <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
        Packaged desktop uses only the Vite UI. The legacy web runtime is no
        longer bundled, and no bundled Node process is expected.
      </p>
    </Card>
  );
}

function LocalPathsCard({
  paths,
  desktopMode,
  openingKind,
  openError,
  copiedKind,
  copyError,
  onOpen,
  onCopy,
}: {
  paths: AppStatusPayload["paths"];
  desktopMode: boolean;
  openingKind: StatusPathKind | null;
  openError: unknown;
  copiedKind: string | null;
  copyError: string | null;
  onOpen: (kind: StatusPathKind) => void;
  onCopy: (kind: string, path: string) => void;
}) {
  const rows = PATH_ORDER.map((kind) => paths[kind]).filter(Boolean) as LocalPathInfo[];
  return (
    <Card title="Local Data" eyebrow="Persistent paths">
      <div className="space-y-3">
        {rows.map((item) => (
          <div key={item.kind} className="rounded border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-wider text-zinc-500">
                  {pathLabel(item.kind)}
                </p>
                <p className="mt-1 break-all font-mono text-xs leading-5 text-zinc-200">
                  {item.path}
                </p>
                <p className="mt-1 text-[11px] text-zinc-500">
                  {item.exists ? "Exists" : "Not created yet"}
                  {item.is_file ? " · file" : item.is_dir ? " · folder" : ""}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={() => onCopy(item.kind, item.path)}
                  className="rounded border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
                >
                  {copiedKind === item.kind ? "Copied" : "Copy"}
                </button>
                <button
                  type="button"
                  disabled={!desktopMode || openingKind === item.kind}
                  onClick={() => onOpen(item.kind as StatusPathKind)}
                  className="rounded border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:border-zinc-500 hover:text-zinc-100 disabled:cursor-not-allowed disabled:border-zinc-800 disabled:text-zinc-600"
                >
                  {!desktopMode ? "Desktop only" : openingKind === item.kind ? "Opening" : "Open"}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
      {copyError ? <InlineError>{copyError}</InlineError> : null}
      {openError ? (
        <InlineError>
          {openError instanceof Error ? openError.message : String(openError)}
        </InlineError>
      ) : null}
      {!desktopMode ? (
        <p className="mt-3 text-xs text-amber-200">
          Opening local folders is unsupported in browser preview.
        </p>
      ) : null}
    </Card>
  );
}

function DatabaseCard({ database }: { database: DatabaseDiagnostics | null }) {
  if (!database) {
    return (
      <Card title="Database" eyebrow="SQLite" tone="warn">
        <p className="text-sm text-zinc-400">Database status requires the desktop bridge.</p>
      </Card>
    );
  }
  const rows = database.row_counts;
  const tone = database.error ? "bad" : database.db_exists && !database.is_empty ? "good" : "warn";
  return (
    <Card title="Database" eyebrow="Local SQLite" tone={tone}>
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Companies" value={formatInt(rows.companies)} />
        <Metric label="Financial reports" value={formatInt(rows.financial_reports)} />
        <Metric label="DB size" value={formatBytes(database.db_size_bytes)} />
        <Metric label="Refresh jobs" value={formatInt(rows.refresh_jobs)} />
        <Metric label="QA logs" value={formatInt(rows.qa_logs)} />
        <Metric label="Refresh errors" value={formatInt(database.refresh_errors_count)} tone={database.refresh_errors_count ? "bad" : "neutral"} />
      </div>
      <dl className="mt-4 grid gap-3 border-t border-zinc-800 pt-3 text-sm sm:grid-cols-2">
        <Field label="Status" value={database.db_exists ? (database.is_empty ? "exists, no financial data" : "populated") : "file missing"} tone={tone === "bad" ? "bad" : tone === "good" ? "good" : "warn"} />
        <Field label="Latest report" value={formatReportPeriod(database)} />
        <Field label="Last success" value={formatDateTime(database.latest_success_at)} />
        <Field label="Last attempt" value={formatDateTime(database.latest_attempt_at)} />
      </dl>
      {database.latest_error ? (
        <InlineError>Latest refresh error: {database.latest_error}</InlineError>
      ) : null}
      {database.error ? <InlineError>{database.error}</InlineError> : null}
    </Card>
  );
}

function UpdateCard({
  update,
  checking,
  onCheckUpdates,
}: {
  update: UpdateStatus | null;
  checking: boolean;
  onCheckUpdates: () => void;
}) {
  const tone = updateTone(update);
  const [showConfirm, setShowConfirm] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [progress, setProgress] = useState<UpdateProgressStatus | null>(update?.progress ?? null);
  const [isApplying, setIsApplying] = useState(false);

  // Sync initial/updated progress from props
  useEffect(() => {
    if (update?.progress) {
      setProgress(update.progress);
    }
  }, [update?.progress]);

  // Poll update progress if status is downloading or swapping
  useEffect(() => {
    let intervalId: any = null;
    const currentStatus = progress?.status;
    const active = currentStatus === "downloading" || currentStatus === "swapping";

    if (active) {
      setIsApplying(true);
      intervalId = setInterval(async () => {
        try {
          const prog = await fetchUpdateProgress();
          setProgress(prog);
          if (prog.status === "error") {
            setLocalError(prog.error || "Error during update");
            setIsApplying(false);
            clearInterval(intervalId);
          } else if (prog.status === "idle" || prog.status === "success") {
            setIsApplying(false);
            clearInterval(intervalId);
          }
        } catch (err) {
          setLocalError(err instanceof Error ? err.message : String(err));
          setIsApplying(false);
          clearInterval(intervalId);
        }
      }, 1000);
    } else {
      setIsApplying(false);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [progress?.status]);

  const handleApplyUpdate = async () => {
    setLocalError(null);
    setShowConfirm(false);
    setIsApplying(true);
    setProgress({ status: "downloading", percent: 0, error: null });
    try {
      const result = await triggerApplyUpdate();
      if (!result.started) {
        setLocalError(result.error || "Could not start the update.");
        setIsApplying(false);
        setProgress(null);
      }
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
      setIsApplying(false);
      setProgress(null);
    }
  };

  const hasUpdate = update?.update_available;
  const canApply = update?.apply_supported && !isApplying;

  return (
    <Card title="Software update" eyebrow="GitHub Releases" tone={tone}>
      {!update ? (
        <p className="text-sm text-zinc-400">Updater status unavailable.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <StatusPill tone={tone}>{updateLabel(update)}</StatusPill>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <Field label="Current" value={update.current_version ?? "unknown"} mono />
                <Field label="Latest" value={update.latest_version ?? "unknown"} mono />
                <Field label="Checked" value={formatDateTime(update.checked_at ?? null)} />
                <Field
                  label="Install from Vite"
                  value={update.apply_supported ? "supported" : "not supported"}
                  tone={update.apply_supported ? "good" : "warn"}
                />
              </dl>
            </div>
            {!isApplying && (
              <button
                type="button"
                disabled={checking}
                onClick={onCheckUpdates}
                className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:border-cyan-700 hover:text-cyan-100 disabled:cursor-not-allowed disabled:text-zinc-600 font-mono"
              >
                {checking ? "Checking..." : "Check now"}
              </button>
            )}
          </div>

          {hasUpdate && canApply && !showConfirm && (
            <div className="mt-4">
              <button
                type="button"
                onClick={() => setShowConfirm(true)}
                className="w-full sm:w-auto rounded bg-cyan-600 hover:bg-cyan-500 px-4 py-2 text-xs font-semibold text-white transition-colors"
              >
                Install Update
              </button>
            </div>
          )}

          {showConfirm && (
            <div className="mt-4 rounded border border-amber-500/20 bg-amber-500/5 p-4 space-y-3">
              <h4 className="text-xs uppercase tracking-wider font-semibold text-amber-200">
                Confirm Software Update
              </h4>
              <p className="text-xs text-zinc-300 leading-relaxed">
                The app will close and restart to apply version{" "}
                <span className="font-mono text-zinc-100 font-semibold">
                  {update.latest_version}
                </span>
                . Your local data (database, reports, and exported spreadsheets) will be preserved.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleApplyUpdate}
                  className="rounded bg-amber-600 hover:bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white transition-colors"
                >
                  Confirm and Close App
                </button>
                <button
                  type="button"
                  onClick={() => setShowConfirm(false)}
                  className="rounded border border-zinc-750 hover:border-zinc-500 px-3 py-1.5 text-xs font-semibold text-zinc-300 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {isApplying && (
            <div className="mt-4 rounded border border-cyan-500/20 bg-cyan-950/40 p-4 space-y-3">
              <div className="flex justify-between items-center text-xs">
                <span className="font-semibold text-cyan-200 capitalize">
                  {progress?.status === "downloading"
                    ? "Downloading update..."
                    : progress?.status === "swapping"
                      ? "Replacing files..."
                      : "Preparing..."}
                </span>
                <span className="font-mono text-cyan-100 font-bold">{progress?.percent ?? 0}%</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-cyan-500 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${progress?.percent ?? 0}%` }}
                />
              </div>
              <p className="text-[11px] text-zinc-400">
                Please do not close the app. The process will complete automatically.
              </p>
            </div>
          )}

          {update.release_url && !isApplying && !showConfirm ? (
            <a
              href={update.release_url}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:border-zinc-500 hover:text-zinc-100 transition-colors"
            >
              Open release page
            </a>
          ) : null}

          {(localError || update.error) && (
            <InlineError>
              {localError ||
                (update.status === "check_failed"
                  ? "Could not check GitHub Releases. Check your internet connection or try again later."
                  : update.error)}
            </InlineError>
          )}

          <div className="mt-4 border-t border-zinc-800 pt-3 text-[11px] leading-relaxed text-zinc-500 space-y-2">
            <p>
              <span className="font-semibold text-zinc-400">Note:</span> This update changes the software version via GitHub Releases.
              To update company data (CVM financial statements), use the{" "}
              <a
                href="#/settings/updates"
                className="font-semibold text-zinc-300 underline decoration-zinc-600 underline-offset-2 hover:text-cyan-100"
              >
                Database Updates
              </a>{" "}
              page.
            </p>
          </div>
        </>
      )}
    </Card>
  );
}

function DiagnosticsCard({ diagnostics }: { diagnostics: DiagnosticsSummary }) {
  const tone = diagnostics.errors.length ? "bad" : diagnostics.warnings.length ? "warn" : "good";
  return (
    <Card title="Runtime diagnostics" eyebrow="Local probes" tone={tone}>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <Field label=".NET" value={diagnostics.dotnet_status ?? "unknown"} tone={fieldTone(diagnostics.dotnet_status)} />
        <Field label="WebView2" value={diagnostics.webview2_version ?? "not detected"} tone={diagnostics.webview2_version ? "good" : "warn"} />
        <Field label="pythonnet" value={diagnostics.pythonnet_status ?? "unknown"} tone={fieldTone(diagnostics.pythonnet_status)} />
        <Field label="SQLite" value={diagnostics.sqlite_status ?? "unknown"} tone={fieldTone(diagnostics.sqlite_status)} />
      </dl>
      {(diagnostics.data_root || diagnostics.db_path) && (
        <dl className="mt-3 grid gap-2 border-t border-zinc-800 pt-3 text-sm">
          {diagnostics.data_root && <Field label="Data directory" value={diagnostics.data_root} mono />}
          {diagnostics.db_path && <Field label="Database" value={diagnostics.db_path} mono />}
        </dl>
      )}
      <DiagnosticsList title="Errors" items={diagnostics.errors} tone="bad" />
      <DiagnosticsList title="Warnings" items={diagnostics.warnings} tone="warn" />
      {diagnostics.errors.length === 0 && diagnostics.warnings.length === 0 ? (
        <p className="mt-4 rounded border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm text-emerald-100">
          Runtime probes completed with no warnings.
        </p>
      ) : null}
    </Card>
  );
}

function RecentDiagnostics({ entries }: { entries: DiagnosticLogEntry[] }) {
  return (
    <Card title="Recent warnings / logs" eyebrow="Compact tail">
      {entries.length === 0 ? (
        <p className="text-sm text-zinc-500">No recent recovery, update, or refresh warnings found.</p>
      ) : (
        <ol className="divide-y divide-zinc-800 rounded border border-zinc-800 bg-zinc-950/50">
          {entries.map((entry, index) => (
            <li key={`${entry.source}-${entry.timestamp ?? index}-${index}`} className="grid gap-2 p-3 sm:grid-cols-[7rem_8rem_minmax(0,1fr)]">
              <span className={logSeverityClass(entry.severity)}>{entry.severity}</span>
              <span className="font-mono text-[11px] text-zinc-500">{entry.source}</span>
              <span className="min-w-0 text-xs leading-5 text-zinc-300">
                <span className="mr-2 text-zinc-500">{formatDateTime(entry.timestamp ?? null)}</span>
                {entry.message}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function LoadingState() {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {[0, 1, 2, 3].map((item) => (
        <article key={item} className="min-h-44 rounded-lg border border-zinc-800 bg-zinc-900/60 p-5">
          <div className="h-3 w-28 rounded bg-zinc-800" />
          <div className="mt-5 h-6 w-48 rounded bg-zinc-800" />
          <div className="mt-4 space-y-2">
            <div className="h-3 rounded bg-zinc-800/80" />
            <div className="h-3 w-3/4 rounded bg-zinc-800/80" />
          </div>
        </article>
      ))}
    </div>
  );
}

function BrowserFallback({ reason }: { reason: string }) {
  return (
    <Alert tone="warning" title="Browser preview fallback">
      {reason} Local paths, GitHub updater status, and runtime probes are placeholders here.
    </Alert>
  );
}

function Card({
  title,
  eyebrow,
  tone = "neutral",
  children,
}: {
  title: string;
  eyebrow: string;
  tone?: Tone;
  children: ReactNode;
}) {
  const border =
    tone === "good"
      ? "border-emerald-500/20"
      : tone === "warn"
        ? "border-amber-500/30"
        : tone === "bad"
          ? "border-rose-500/30"
          : "border-zinc-800";
  return (
    <article className={`rounded-lg border ${border} bg-zinc-900/60 p-5 shadow-lg`}>
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-zinc-500">{eyebrow}</p>
          <h3 className="mt-1 text-lg font-semibold text-zinc-100">{title}</h3>
        </div>
      </header>
      {children}
    </article>
  );
}

function Alert({
  tone,
  title,
  children,
}: {
  tone: "warning" | "error";
  title: string;
  children: ReactNode;
}) {
  const cls =
    tone === "error"
      ? "border-rose-900/60 bg-rose-950/40 text-rose-200"
      : "border-amber-500/30 bg-amber-500/10 text-amber-100";
  return (
    <article className={`rounded-lg border p-4 text-sm ${cls}`}>
      <p className="font-medium">{title}</p>
      <p className="mt-1 opacity-85">{children}</p>
    </article>
  );
}

function Field({
  label,
  value,
  tone = "neutral",
  mono = false,
}: {
  label: string;
  value: string;
  tone?: Tone;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className={`mt-1 break-words text-sm ${mono ? "font-mono" : ""} ${toneText(tone)}`}>
        {value}
      </dd>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/50 p-3">
      <p className="text-[11px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`mt-1 font-mono text-base font-semibold ${toneText(tone)}`}>{value}</p>
    </div>
  );
}

function StatusPill({
  tone,
  children,
}: {
  tone: Tone;
  children: ReactNode;
}) {
  const cls =
    tone === "good"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
      : tone === "warn"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-100"
        : tone === "bad"
          ? "border-rose-500/30 bg-rose-500/10 text-rose-200"
          : "border-zinc-700 bg-zinc-950/70 text-zinc-300";
  return <span className={`rounded-full border px-3 py-1 text-xs ${cls}`}>{children}</span>;
}

function InlineError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mt-3 rounded border border-rose-900/60 bg-rose-950/40 p-3 text-xs leading-5 text-rose-300">
      {children}
    </p>
  );
}

function DiagnosticsList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "warn" | "bad";
}) {
  if (items.length === 0) return null;
  return (
    <div className="mt-4">
      <p className={`text-xs uppercase tracking-wider ${toneText(tone)}`}>{title}</p>
      <ul className="mt-2 space-y-2">
        {items.slice(0, 4).map((item) => (
          <li key={item} className="rounded border border-zinc-800 bg-zinc-950/50 p-3 text-xs leading-5 text-zinc-300">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function lockStatusLabel(lock: LockStatusPayload): string {
  if (lock.status === "locked_by_self") return "locked by this process";
  if (lock.status === "locked_by_other") {
    const pid = lock.pid ? ` (PID ${lock.pid})` : "";
    const mode = lock.runtime_mode ? ` · ${lock.runtime_mode}` : "";
    return `locked by another process${pid}${mode}`;
  }
  if (lock.status === "stale_recovered") {
    return lock.stale_pid ? `stale lock recovered (was PID ${lock.stale_pid})` : "stale lock recovered";
  }
  if (lock.status === "no_lock") return "no lock";
  return lock.status;
}

function lockStatusTone(lock: LockStatusPayload): Tone {
  if (lock.status === "locked_by_self") return "good";
  if (lock.status === "locked_by_other") return "bad";
  if (lock.status === "stale_recovered") return "warn";
  return "neutral";
}

type Tone = "neutral" | "good" | "warn" | "bad";

function toneText(tone: Tone): string {
  if (tone === "good") return "text-emerald-200";
  if (tone === "warn") return "text-amber-200";
  if (tone === "bad") return "text-rose-300";
  return "text-zinc-100";
}

function fieldTone(value: string | null | undefined): Tone {
  const normalized = String(value ?? "").toLowerCase();
  if (normalized.startsWith("ok")) return "good";
  if (normalized.startsWith("error") || normalized.includes("failed")) return "bad";
  if (normalized.includes("not_detected") || normalized.includes("pre_")) return "warn";
  return "neutral";
}

function updateTone(update: UpdateStatus | null): Tone {
  if (!update) return "warn";
  if (update.status === "available") return "warn";
  if (update.status === "check_failed" || update.status === "asset_missing") return "bad";
  if (update.status === "up_to_date") return "good";
  return "neutral";
}

function updateLabel(update: UpdateStatus): string {
  if (update.status === "available") return "Update available";
  if (update.status === "up_to_date") return "Up to date";
  if (update.status === "check_failed") return "Update check failed";
  if (update.status === "asset_missing") return "Release asset missing";
  if (update.status === "snoozed") return "Update snoozed";
  if (update.status === "available_cached") return "Update available (cached)";
  return update.status.replace(/_/g, " ");
}

function logSeverityClass(severity: string): string {
  const base = "rounded-full border px-2 py-0.5 text-center text-[11px] capitalize";
  if (severity === "error") return `${base} border-rose-500/30 text-rose-200`;
  if (severity === "warning") return `${base} border-amber-500/30 text-amber-200`;
  return `${base} border-zinc-700 text-zinc-400`;
}

function pathLabel(kind: string): string {
  if (kind === "data") return "Data root";
  if (kind === "database") return "Database";
  if (kind === "output") return "Output";
  if (kind === "logs") return "Logs";
  if (kind === "cache") return "Cache";
  return kind;
}

function formatBytes(bytes: number | null | undefined): string {
  if (!Number.isFinite(bytes) || Number(bytes) <= 0) return "0 bytes";
  const units = ["bytes", "KB", "MB", "GB"];
  let value = Number(bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatInt(value: number | null | undefined): string {
  if (value == null) return "n/a";
  return new Intl.NumberFormat("en-US").format(value);
}

function formatDateTime(value: string | null): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatReportPeriod(database: DatabaseDiagnostics): string {
  if (database.latest_report_year == null) return "n/a";
  return database.latest_period_label
    ? `${database.latest_report_year} · ${database.latest_period_label}`
    : String(database.latest_report_year);
}
