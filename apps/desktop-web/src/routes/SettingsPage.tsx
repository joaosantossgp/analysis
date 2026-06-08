import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import {
  fetchAppStatus,
  openStatusPath,
  type StatusPathKind,
} from "@/lib/api/appStatus";
import { fetchPlantParcelSourceStatuses } from "@/lib/api/energyKpis";
import { whenBridgeReady, type BridgeMode } from "@/lib/bridge/adapter";
import type {
  AppStatusPayload,
  PlantParcelSourceStatus,
  PlantParcelSourceStatusResponse,
} from "@/lib/bridge/types";

const CCEE_SOURCE_IDS = ["ccee_plant_parcel_monthly", "ccee_plant_generation_hourly"];

export function SettingsPage() {
  const [bridgeMode, setBridgeMode] = useState<BridgeMode | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then((mode) => {
      if (!cancelled) setBridgeMode(mode);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const statusQuery = useQuery({
    queryKey: ["settings-app-status"],
    queryFn: () => fetchAppStatus(),
    enabled: bridgeMode !== null,
    staleTime: 30_000,
  });

  const plantSourcesQuery = useQuery({
    queryKey: ["settings-plant-parcel-sources", CCEE_SOURCE_IDS],
    queryFn: () => fetchPlantParcelSourceStatuses({ source_ids: CCEE_SOURCE_IDS }),
    enabled: bridgeMode !== null,
    staleTime: 30_000,
  });

  const openMutation = useMutation({ mutationFn: openStatusPath });
  const status = statusQuery.data?.status ?? null;
  const plantResponse =
    plantSourcesQuery.data?.mode === "desktop" ? plantSourcesQuery.data.response : null;
  const plantSources =
    plantSourcesQuery.data?.mode === "desktop" ? plantSourcesQuery.data.statuses : [];
  const browserReason =
    statusQuery.data?.mode === "browser"
      ? statusQuery.data.reason
      : plantSourcesQuery.data?.mode === "browser"
        ? plantSourcesQuery.data.reason
        : null;

  const localBases = useMemo(
    () => buildLocalBases(status, plantResponse),
    [status, plantResponse],
  );

  async function copyPath(key: string, path: string) {
    setCopyError(null);
    try {
      await navigator.clipboard.writeText(path);
      setCopiedKey(key);
    } catch {
      setCopyError("Could not copy path. Select the path text manually.");
    }
  }

  const loading = bridgeMode === null || statusQuery.isLoading;

  return (
    <section className="space-y-5 rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <PageHeader
        title="Settings"
        subtitle="Local data root, active databases, and user-managed source files."
        breadcrumbs={[{ label: "Settings" }]}
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={!status?.paths.data || openMutation.isPending}
              loading={openMutation.isPending && openMutation.variables === "data"}
              onClick={() => openMutation.mutate("data")}
            >
              Open data folder
            </Button>
            <LinkButton to="/status">Diagnostics</LinkButton>
          </div>
        }
      />

      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}

      {loading || !status ? (
        <StateBanner variant="loading" title="Loading settings..." />
      ) : (
        <>
          {status.runtime.using_release_data_dir && !status.runtime.frozen ? (
            <StateBanner
              variant="warning"
              title="Dev is using the shared Documents data root"
              message="Destructive actions are blocked by default in this mode."
            />
          ) : null}

          {statusQuery.error ? (
            <StateBanner
              variant="error"
              title="Could not load runtime settings"
              message={errorText(statusQuery.error)}
            />
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <LocalBasesCard
              bases={localBases}
              paths={status.paths}
              openingKind={openMutation.isPending ? (openMutation.variables ?? null) : null}
              openError={openMutation.error}
              copiedKey={copiedKey}
              copyError={copyError}
              onOpen={(kind) => openMutation.mutate(kind)}
              onCopy={copyPath}
            />
            <RuntimeSettingsCard status={status} />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <UserImportsCard
              sources={plantSources}
              loading={plantSourcesQuery.isLoading}
              error={plantSourcesQuery.error}
            />
            <ManagedSourcesCard status={status} plantResponse={plantResponse} />
          </div>
        </>
      )}
    </section>
  );
}

type LocalBase = {
  key: string;
  label: string;
  path: string;
  exists?: boolean;
  detail: string;
  openKind?: StatusPathKind;
};

function buildLocalBases(
  status: AppStatusPayload | null,
  plantResponse: PlantParcelSourceStatusResponse | null,
): LocalBase[] {
  if (!status) return [];
  const bases: LocalBase[] = [];
  const data = status.paths.data;
  const database = status.paths.database;
  if (data) {
    bases.push({
      key: "data-root",
      label: "Data root",
      path: data.path,
      exists: data.exists,
      detail: "Primary runtime directory.",
      openKind: "data",
    });
  }
  if (database) {
    bases.push({
      key: "cvm-database",
      label: "CVM financial database",
      path: database.path,
      exists: database.exists,
      detail: "Company filings, statements, refresh jobs, and app settings.",
      openKind: "database",
    });
  }
  if (plantResponse?.database_path) {
    bases.push({
      key: "energy-database",
      label: "Energy indicators database",
      path: plantResponse.database_path,
      exists: true,
      detail: "Macro energy, SIN, and Plant Parcels cache.",
    });
  }
  if (plantResponse?.raw_data_dir) {
    bases.push({
      key: "energy-raw",
      label: "Energy raw/import files",
      path: plantResponse.raw_data_dir,
      exists: true,
      detail: "Downloaded and manually imported energy source files.",
    });
  }
  return bases;
}

function LocalBasesCard({
  bases,
  paths,
  openingKind,
  openError,
  copiedKey,
  copyError,
  onOpen,
  onCopy,
}: {
  bases: LocalBase[];
  paths: AppStatusPayload["paths"];
  openingKind: StatusPathKind | null;
  openError: unknown;
  copiedKey: string | null;
  copyError: string | null;
  onOpen: (kind: StatusPathKind) => void;
  onCopy: (key: string, path: string) => void;
}) {
  return (
    <Card title="Local Bases" eyebrow="Active paths">
      <div className="space-y-3">
        {bases.map((base) => (
          <div key={base.key} className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-xs uppercase tracking-wider text-zinc-500">{base.label}</p>
                  <StatusPill tone={base.exists === false ? "warn" : "good"}>
                    {base.exists === false ? "missing" : "available"}
                  </StatusPill>
                </div>
                <p className="mt-1 break-all font-mono text-xs leading-5 text-zinc-200">{base.path}</p>
                <p className="mt-1 text-xs text-zinc-500">{base.detail}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {base.openKind ? (
                  <Button
                    size="xs"
                    variant="secondary"
                    loading={openingKind === base.openKind}
                    onClick={() => onOpen(base.openKind!)}
                  >
                    Open
                  </Button>
                ) : null}
                <Button size="xs" variant="ghost" onClick={() => onCopy(base.key, base.path)}>
                  {copiedKey === base.key ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
          </div>
        ))}
        {copyError ? <InlineNotice tone="warning">{copyError}</InlineNotice> : null}
        {openError ? <InlineNotice tone="error">{errorText(openError)}</InlineNotice> : null}
        {!paths.data ? (
          <StateBanner
            variant="warning"
            title="Data root unavailable"
            message="Runtime path diagnostics are not available in this mode."
            size="dense"
          />
        ) : null}
      </div>
    </Card>
  );
}

function RuntimeSettingsCard({ status }: { status: AppStatusPayload }) {
  return (
    <Card title="Runtime Configuration" eyebrow="Effective mode">
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <Field label="Mode" value={runtimeModeLabel(status.runtime.runtime_mode)} />
        <Field label="Version" value={status.runtime.version} mono />
        <Field
          label="Write mode"
          value={status.runtime.write_mode ?? "unknown"}
          tone={status.runtime.write_mode === "read-only" ? "warn" : "neutral"}
        />
        <Field
          label="Shared data"
          value={status.runtime.using_release_data_dir ? "yes" : "no"}
          tone={status.runtime.using_release_data_dir ? "good" : "warn"}
        />
        <Field label="Database rows" value={formatNumber(status.database?.row_counts.financial_reports)} mono />
        <Field label="Companies" value={formatNumber(status.database?.row_counts.companies)} mono />
      </dl>
      <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/50 p-3 text-xs leading-5 text-zinc-500">
        <p>
          `CVM_DATA_DIR`, `CVM_DB_DIR`, `SQLITE_PATH`, `CVM_ENERGY_KPI_DB`, and
          `CVM_ENERGY_KPI_RAW_DIR` override these paths before startup.
        </p>
      </div>
    </Card>
  );
}

function UserImportsCard({
  sources,
  loading,
  error,
}: {
  sources: PlantParcelSourceStatus[];
  loading: boolean;
  error: unknown;
}) {
  const importSources = sources.filter((source) => CCEE_SOURCE_IDS.includes(source.source_id));
  return (
    <Card title="User Imports" eyebrow="Source files">
      {loading ? <StateBanner variant="loading" title="Loading source status..." size="dense" /> : null}
      {error ? (
        <StateBanner
          variant="error"
          title="Could not load source status"
          message={errorText(error)}
          size="dense"
        />
      ) : null}
      <div className="space-y-3">
        {importSources.map((source) => (
          <SourceImportRow key={source.source_id} source={source} />
        ))}
        {!loading && !error && importSources.length === 0 ? (
          <StateBanner
            variant="empty"
            title="No user-imported sources"
            message="No CCEE import sources were reported by the local bridge."
            size="dense"
          />
        ) : null}
      </div>
    </Card>
  );
}

function SourceImportRow({ source }: { source: PlantParcelSourceStatus }) {
  const lastFile = source.last_manual_file_name ?? source.last_original_file_name;
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs uppercase tracking-wider text-zinc-500">{source.provider}</p>
            <StatusPill tone={source.cache_status === "failed" ? "bad" : source.cache_status === "never_refreshed" ? "warn" : "good"}>
              {statusLabel(source.cache_status)}
            </StatusPill>
          </div>
          <h3 className="mt-1 text-sm font-semibold text-zinc-100">{source.source_name}</h3>
          <p className="mt-1 font-mono text-xs text-zinc-500">{source.dataset_name}</p>
        </div>
        <LinkButton to="/indicators?view=plants">Open import</LinkButton>
      </div>
      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <Field label="Records" value={formatNumber(source.local_records_count)} mono />
        <Field label="Latest ref" value={source.latest_reference ?? "—"} mono />
        <Field label="Last import" value={formatDateTime(source.last_manual_import_at ?? source.last_refresh_at)} />
        <Field label="Last file" value={lastFile ?? "—"} mono />
      </dl>
      {source.last_manual_error || source.last_error ? (
        <InlineNotice tone="error">{source.last_manual_error ?? source.last_error}</InlineNotice>
      ) : null}
      {source.last_manual_warning || source.last_warning ? (
        <InlineNotice tone="warning">{source.last_manual_warning ?? source.last_warning}</InlineNotice>
      ) : null}
    </div>
  );
}

function ManagedSourcesCard({
  status,
  plantResponse,
}: {
  status: AppStatusPayload;
  plantResponse: PlantParcelSourceStatusResponse | null;
}) {
  const rowCount = plantResponse?.source_statuses?.length ?? 0;
  return (
    <Card title="Managed Sources" eyebrow="App-maintained">
      <div className="space-y-3">
        <ManagedSourceRow
          title="CVM filings database"
          label="Financial statements and company directory"
          status={status.database?.row_counts.financial_reports ? "available" : "needs update"}
          details={`${formatNumber(status.database?.row_counts.financial_reports)} financial rows · ${formatNumber(status.database?.row_counts.companies)} companies`}
          to="/atualizar-base"
          action="Update base"
        />
        <ManagedSourceRow
          title="Data coverage"
          label="Completeness monitor for company/year filings"
          status={status.database ? "available" : "unavailable"}
          details="Tracks missing, failed, ignored, and complete company coverage."
          to="/data-coverage"
          action="View coverage"
        />
        <ManagedSourceRow
          title="Energy source catalog"
          label="Source metadata for indicators and Plant Parcels"
          status={rowCount > 0 ? "available" : "unavailable"}
          details={`${formatNumber(rowCount)} source definitions reported by the energy database.`}
          to="/indicators"
          action="Open indicators"
        />
      </div>
    </Card>
  );
}

function ManagedSourceRow({
  title,
  label,
  status,
  details,
  to,
  action,
}: {
  title: string;
  label: string;
  status: string;
  details: string;
  to: string;
  action: string;
}) {
  const tone = status === "available" ? "good" : status === "needs update" ? "warn" : "bad";
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs uppercase tracking-wider text-zinc-500">{label}</p>
            <StatusPill tone={tone}>{status}</StatusPill>
          </div>
          <h3 className="mt-1 text-sm font-semibold text-zinc-100">{title}</h3>
          <p className="mt-1 text-xs text-zinc-500">{details}</p>
        </div>
        <LinkButton to={to}>{action}</LinkButton>
      </div>
    </div>
  );
}

function Card({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow: string;
  children: ReactNode;
}) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 shadow-lg">
      <p className="text-xs uppercase tracking-wider text-zinc-500">{eyebrow}</p>
      <h2 className="mt-1 text-base font-semibold text-zinc-100">{title}</h2>
      <div className="mt-4">{children}</div>
    </article>
  );
}

function Field({
  label,
  value,
  mono,
  tone = "neutral",
}: {
  label: string;
  value: string | number | null | undefined;
  mono?: boolean;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  const color =
    tone === "good"
      ? "text-emerald-200"
      : tone === "warn"
        ? "text-amber-200"
        : tone === "bad"
          ? "text-red-200"
          : "text-zinc-100";
  return (
    <div className="min-w-0">
      <dt className="text-xs uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className={`mt-1 break-words text-sm ${mono ? "font-mono" : ""} ${color}`}>
        {value ?? "—"}
      </dd>
    </div>
  );
}

function StatusPill({
  tone,
  children,
}: {
  tone: "good" | "warn" | "bad" | "neutral";
  children: ReactNode;
}) {
  const klass =
    tone === "good"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
      : tone === "warn"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
        : tone === "bad"
          ? "border-red-500/30 bg-red-500/10 text-red-200"
          : "border-zinc-700 bg-zinc-900 text-zinc-300";
  return (
    <span className={`rounded border px-2 py-0.5 font-mono text-[11px] uppercase ${klass}`}>
      {children}
    </span>
  );
}

function InlineNotice({
  tone,
  children,
}: {
  tone: "warning" | "error";
  children: ReactNode;
}) {
  const klass =
    tone === "error"
      ? "border-red-500/30 bg-red-500/10 text-red-200"
      : "border-amber-500/30 bg-amber-500/10 text-amber-200";
  return <p className={`mt-3 rounded border px-3 py-2 text-xs ${klass}`}>{children}</p>;
}

function LinkButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex h-7 items-center justify-center rounded-md border border-zinc-700 px-3 text-xs font-medium text-zinc-200 hover:border-cyan-700 hover:text-cyan-100"
    >
      {children}
    </Link>
  );
}

function runtimeModeLabel(mode: string): string {
  if (mode === "vite-dev-release-data") return "vite dev · shared data";
  if (mode === "vite-dev") return "vite dev";
  if (mode === "vite") return "desktop";
  return mode || "unknown";
}

function statusLabel(value: string | null | undefined): string {
  if (!value) return "unknown";
  return value.replaceAll("_", " ");
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("en-US").format(Number(value));
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
