import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useExportAction } from "@/components/export/useExportAction";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { openCompanyExcelMappingWindow } from "@/lib/api/companyWindows";
import {
  companyRefreshProgress,
  fetchCompanyRefreshStatus,
  isActiveCompanyRefresh,
  normalizedTrackingState,
  requestCompanyRefresh,
  type CompanyRefreshStatusResult,
} from "@/lib/api/companyRefresh";
import {
  fetchCompanyInfo,
  type CompanyInfoResult,
} from "@/lib/api/companyDetail";
import {
  triggerAllMarketHistoryRefresh,
  type MarketHistoryAllRefreshResultUI,
} from "@/lib/api/marketHistory";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type {
  CompanyMarketHistoryAllRefreshResult,
  CompanyRefreshStatus,
  RefreshDispatchResponse,
} from "@/lib/bridge/types";
import { useLocalDatabaseState } from "@/lib/api/localDatabase";

const ACTIVE_POLL_MS = 2_000;
const CVM_MIN_YEAR = 2010;

const PERIOD_SCOPE_OPTIONS = [
  { value: "last_3_years", label: "3 years" },
  { value: "last_5_years", label: "5 years" },
  { value: "last_10_years", label: "10 years" },
  { value: "full_history", label: "Full history" },
] as const;

type HistoryScope = (typeof PERIOD_SCOPE_OPTIONS)[number]["value"];

/**
 * Label of the company update (Company update in GLOSSARY.md). Its scope is one
 * company, so it is never called "Update data" (that is the data update).
 */
export function companyActionLabel({ queued, pending, failed }: { queued: boolean; pending: boolean; failed: boolean }): string {
  if (pending) return "Updating company";
  if (failed) return "Retry update";
  return queued ? "Download now" : "Update company";
}

export function historyPresetRange(scope: HistoryScope, endYear: number) {
  const startYear =
    scope === "last_3_years"
      ? endYear - 2
      : scope === "last_5_years"
        ? endYear - 4
        : scope === "last_10_years"
          ? endYear - 9
          : CVM_MIN_YEAR;
  return { startYear, endYear };
}

export const COMPANY_COMMAND_LABELS = {
  statements: "Statements",
  excelMappingWindow: "Open Excel Mapping in a separate window",
  historyDisclosure: "History range",
  marketPrices: "Update market prices (external)",
  refreshDetails: "Refresh details",
} as const;

export function getCompanyCommandWorkspaceLinks(cdCvm: number) {
  return [
    {
      label: COMPANY_COMMAND_LABELS.statements,
      to: `/empresas/${cdCvm}/demonstrativos`,
    },
  ];
}

type RefreshAction =
  | { type: "incremental" }
  | { type: "history"; startYear: number; endYear: number };

type Props = {
  cdCvm: number;
  bridgeReady?: boolean;
  latestPeriod?: string | null;
  yearsAvailable?: number | null;
  lastModelUpdatedAt?: string | null;
  className?: string;
  hideExport?: boolean;
  flat?: boolean;
  compact?: boolean;
  showWorkspaceLinks?: boolean;
  downloadControls?: boolean;
};

export function CompanyExportCard({ cdCvm }: { cdCvm: number }) {
  const [periodScope, setPeriodScope] = useState("last_5_years");
  const [mappingWindowError, setMappingWindowError] = useState<string | null>(null);
  const exportAction = useExportAction({ cdCvm, periodScope });

  async function openMappingWindow() {
    setMappingWindowError(null);
    try {
      const response = await openCompanyExcelMappingWindow(cdCvm);
      if (response.mode === "browser") {
        setMappingWindowError(response.reason);
      } else if (!response.result.ok) {
        setMappingWindowError(response.result.error ?? "Could not open Excel Mapping.");
      }
    } catch (error) {
      setMappingWindowError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <section
      aria-label="Company export"
      style={{ ...barStyle(false, false), display: "flex", height: "100%", position: "relative" }}
    >
      <div className="flex w-full flex-1 flex-col gap-2">
        <label className="flex" aria-label="Export period">
          <Select
            block
            value={periodScope}
            onChange={(event) => setPeriodScope(event.target.value)}
            style={{ fontSize: "var(--text-xs)", height: 24, padding: "1px 22px 1px 7px" }}
          >
            {PERIOD_SCOPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </label>
        <div className="flex min-h-0 flex-1" style={{ paddingBottom: 5, paddingRight: 5 }}>
          <Button
            variant="primary"
            size="xs"
            disabled={!exportAction.isDesktop || exportAction.isRunning}
            loading={exportAction.isRunning}
            onClick={() => exportAction.run()}
            style={{
              borderBottomRightRadius: 0,
              flex: 1,
              height: "100%",
              width: "100%",
            }}
          >
            <SpreadsheetIcon />
            {exportAction.isRunning ? "Exporting" : "Export Excel"}
          </Button>
        </div>
        {exportAction.status === "success" ? (
          <TransientNotice noticeKey={`export:${exportAction.lastRunAt?.getTime() ?? 0}`} tone="success">
            {`Workbook exported${exportAction.result?.file_name ? `: ${exportAction.result.file_name}` : "."}`}
          </TransientNotice>
        ) : exportAction.status === "error" ? (
          <Notice tone="error" role="alert">{exportAction.errorMessage ?? "Export failed."}</Notice>
        ) : null}
        {mappingWindowError ? <Notice tone="error" role="alert">{mappingWindowError}</Notice> : null}
      </div>
      <button
        type="button"
        className="focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan-600"
        aria-label={COMPANY_COMMAND_LABELS.excelMappingWindow}
        title={COMPANY_COMMAND_LABELS.excelMappingWindow}
        onClick={() => void openMappingWindow()}
        style={mappingWindowButtonStyle}
      >
        <OpenInWindowIcon />
      </button>
    </section>
  );
}

export function CompanyCommandBar({
  cdCvm,
  bridgeReady: bridgeReadyProp,
  latestPeriod,
  yearsAvailable,
  lastModelUpdatedAt,
  className,
  hideExport = false,
  flat = false,
  compact: _compact = false,
  showWorkspaceLinks = false,
  downloadControls = false,
}: Props) {
  const [localBridgeReady, setLocalBridgeReady] = useState(false);
  const bridgeReady = bridgeReadyProp ?? localBridgeReady;
  const queryClient = useQueryClient();
  const wasActiveRef = useRef(false);
  const commandBarRef = useRef<HTMLElement | null>(null);
  const currentYear = new Date().getFullYear();

  const [periodScope, setPeriodScope] = useState("last_5_years");
  const [historyScope, setHistoryScope] = useState<HistoryScope>("last_5_years");
  const [showHistory, setShowHistory] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [startYear, setStartYear] = useState(currentYear - 4);
  const [endYear, setEndYear] = useState(currentYear);
  const [yearError, setYearError] = useState<string | null>(null);
  // Queued in a running data update: the company action pulls it ahead.
  const localRun = useLocalDatabaseState().data?.run;
  const queued = Boolean(localRun && localRun.company_ids.includes(cdCvm) && localRun.current_cvm !== cdCvm);

  useEffect(() => {
    if (bridgeReadyProp !== undefined) return;
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setLocalBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [bridgeReadyProp]);

  useEffect(() => {
    if (!downloadControls || !showHistory) return;
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!commandBarRef.current?.contains(event.target as Node)) setShowHistory(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowHistory(false);
    };
    document.addEventListener("mousedown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [downloadControls, showHistory]);

  const infoQuery = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
    enabled:
      bridgeReady &&
      Number.isFinite(cdCvm) &&
      cdCvm > 0 &&
      (latestPeriod === undefined ||
        yearsAvailable === undefined ||
        lastModelUpdatedAt === undefined),
  });

  const info = infoQuery.data?.mode === "desktop" ? infoQuery.data.info : null;
  const statusQuery = useQuery<CompanyRefreshStatusResult>({
    queryKey: ["company-refresh-status", cdCvm],
    queryFn: () => fetchCompanyRefreshStatus(cdCvm),
    enabled: bridgeReady,
    refetchInterval: (query) => {
      const status =
        query.state.data?.mode === "desktop" ? query.state.data.status : null;
      return isActiveCompanyRefresh(status) ? ACTIVE_POLL_MS : false;
    },
  });

  const status =
    statusQuery.data?.mode === "desktop" ? statusQuery.data.status : null;
  const isActive = isActiveCompanyRefresh(status);

  useEffect(() => {
    if (!bridgeReady) return;
    const wasActive = wasActiveRef.current;
    wasActiveRef.current = isActive;
    if (!wasActive || isActive || statusQuery.isFetching) return;
    invalidateCompanyData(queryClient, cdCvm);
  }, [bridgeReady, cdCvm, isActive, queryClient, statusQuery.isFetching]);

  const refreshMutation = useMutation<RefreshDispatchResponse, Error, RefreshAction>({
    mutationFn: (action) => {
      if (action.type === "incremental") {
        return requestCompanyRefresh(cdCvm, {
          startYear: currentYear - 1,
          endYear: currentYear,
        });
      }
      return requestCompanyRefresh(cdCvm, {
        startYear: action.startYear,
        endYear: action.endYear,
      });
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({
        queryKey: ["company-refresh-status", cdCvm],
      });
      if (!result.job_id || result.status === "already_current") {
        invalidateCompanyData(queryClient, cdCvm);
      }
    },
  });

  const marketRefreshMutation = useMutation<MarketHistoryAllRefreshResultUI, Error>({
    mutationFn: () => triggerAllMarketHistoryRefresh(cdCvm),
    onSuccess: () => invalidateMarketHistoryData(queryClient, cdCvm),
  });

  const exportAction = useExportAction({ cdCvm, periodScope });
  const browserReason =
    statusQuery.data?.mode === "browser" ? statusQuery.data.reason : null;
  const latestPeriodLabel =
    latestPeriod ??
    info?.latest_financial_period_display ??
    (status?.latest_readable_year != null ? `FY${status.latest_readable_year}` : null);
  const refreshState =
    !bridgeReady || statusQuery.isLoading ? "loading" : normalizedTrackingState(status);
  const marketRefreshResult =
    marketRefreshMutation.data?.mode === "desktop"
      ? marketRefreshMutation.data.result
      : null;
  const hasMarketRefreshFailure =
    marketRefreshMutation.isError || Boolean(marketRefreshResult && !marketRefreshResult.ok);
  const hasRefreshError =
    statusQuery.isError ||
    refreshMutation.isError ||
    hasMarketRefreshFailure ||
    Boolean(status?.last_error) ||
    refreshState === "error" ||
    refreshState === "stalled";
  const needsAttention =
    Boolean(browserReason) ||
    hasRefreshError ||
    (!latestPeriodLabel && !status?.has_readable_current_data);
  const updateDisabled =
    !bridgeReady || Boolean(browserReason) || refreshMutation.isPending || isActive;
  const marketDisabled = !bridgeReady || Boolean(browserReason) || marketRefreshMutation.isPending;
  const historyDisabled =
    !bridgeReady || Boolean(browserReason) || isActive || refreshMutation.isPending || marketRefreshMutation.isPending;
  const pendingIncremental =
    refreshMutation.isPending && refreshMutation.variables?.type === "incremental";
  const pendingHistory =
    refreshMutation.isPending && refreshMutation.variables?.type === "history";
  const progress = companyRefreshProgress(status);
  const dispatchJobId = refreshMutation.data?.job_id ?? null;
  const statusJobId = status?.job_id ?? null;
  const terminalStateMatchesDispatch = shouldShowRefreshOutcome(
    dispatchJobId,
    statusJobId,
    refreshState,
  );
  const showDispatchNotice = Boolean(refreshMutation.data) && !terminalStateMatchesDispatch;
  const showOutcomeNotice = Boolean(status) && terminalStateMatchesDispatch;
  const hasRefreshFeedback =
    isActive ||
    Boolean(browserReason) ||
    statusQuery.isError ||
    refreshMutation.isError ||
    hasMarketRefreshFailure ||
    Boolean(marketRefreshResult) ||
    showDispatchNotice ||
    showOutcomeNotice;
  const historyId = `company-command-history-${cdCvm}`;
  const detailsId = `company-command-details-${cdCvm}`;
  function validateYears(): boolean {
    if (!Number.isFinite(startYear) || startYear < CVM_MIN_YEAR) {
      setYearError(`Minimum start year: ${CVM_MIN_YEAR}.`);
      return false;
    }
    if (!Number.isFinite(endYear) || endYear > currentYear) {
      setYearError(`Maximum end year: ${currentYear}.`);
      return false;
    }
    if (startYear > endYear) {
      setYearError("Start year must be less than or equal to end year.");
      return false;
    }
    setYearError(null);
    return true;
  }

  function applyPreset(preset: "3y" | "5y" | "10y" | "full") {
    const scope =
      preset === "3y"
        ? "last_3_years"
        : preset === "5y"
          ? "last_5_years"
          : preset === "10y"
            ? "last_10_years"
            : "full_history";
    const range = historyPresetRange(scope, currentYear);
    setStartYear(range.startYear);
    setEndYear(range.endYear);
    setYearError(null);
  }

  function selectHistoryScope(scope: HistoryScope) {
    setHistoryScope(scope);
    const range = historyPresetRange(scope, currentYear);
    setStartYear(range.startYear);
    setEndYear(range.endYear);
    setYearError(null);
  }

  function downloadHistory() {
    if (!validateYears()) return;
    refreshMutation.mutate({ type: "history", startYear, endYear });
  }

  function updateCompanyData() {
    refreshMutation.mutate({ type: "incremental" });
  }

  return (
    <section
      ref={downloadControls ? commandBarRef : undefined}
      className={className}
      aria-label="Company command bar"
      style={{ ...barStyle(needsAttention, flat), ...(downloadControls ? { display: "flex", flexDirection: "column", height: "100%", position: "relative" } : {}) }}
    >
      {downloadControls ? (
        <div className="flex w-full flex-1 flex-col gap-2" style={{ paddingBottom: 5, paddingRight: 5 }}>
          <label className="flex" aria-label="History range">
            <Select
              block
              value={historyScope}
              onChange={(event) => selectHistoryScope(event.target.value as HistoryScope)}
              style={{ fontSize: "var(--text-xs)", height: 24, padding: "1px 22px 1px 7px" }}
            >
              {PERIOD_SCOPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.value === "full_history" ? option.label : `Last ${option.label}`}
                </option>
              ))}
            </Select>
          </label>
          <Button
            variant="primary"
            size="xs"
            disabled={historyDisabled}
            loading={pendingHistory}
            onClick={downloadHistory}
            style={{ flex: 1, minHeight: 34, width: "100%" }}
            title={`CVM statements ${startYear}-${endYear} for this company`}
          >
            <DownloadIcon />
            {companyActionLabel({ queued, pending: pendingHistory, failed: hasRefreshError })}
          </Button>
          <Button
            variant="secondary"
            size="xs"
            disabled={marketDisabled}
            loading={marketRefreshMutation.isPending}
            onClick={() => marketRefreshMutation.mutate()}
            style={{ width: "100%" }}
          >
            <RefreshIcon />
            {COMPANY_COMMAND_LABELS.marketPrices}
          </Button>
        </div>
      ) : (
        <div className={hideExport ? "flex flex-wrap items-center gap-2" : "grid items-start gap-3 sm:grid-cols-[minmax(0,1fr)_172px]"}>
        <div
          className="flex min-w-0 flex-wrap items-center justify-end gap-2"
        >
          {showWorkspaceLinks
            ? getCompanyCommandWorkspaceLinks(cdCvm).map((link) => (
                <CommandLink key={link.to} to={link.to}>
                  {link.label}
                </CommandLink>
              ))
            : null}
          <Button
            variant={hasRefreshError || !latestPeriodLabel ? "danger" : "secondary"}
            size="xs"
            disabled={updateDisabled}
            loading={pendingIncremental}
            onClick={updateCompanyData}
          >
            {companyActionLabel({ queued, pending: pendingIncremental, failed: hasRefreshError })}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            aria-expanded={showHistory}
            aria-controls={historyId}
            onClick={() => setShowHistory((value) => !value)}
          >
            {COMPANY_COMMAND_LABELS.historyDisclosure}
          </Button>
        </div>
        {!hideExport ? (
          <div
            className="flex flex-col gap-2"
            role="group"
            aria-label="Export controls"
            style={{
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              padding: "8px",
            }}
          >
            <span
              style={{
                color: "var(--color-text-tertiary)",
                fontSize: "var(--text-2xs)",
                fontWeight: 600,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
              }}
            >
              Export
            </span>
            <label className="flex" aria-label="Export period">
              <Select
                block
                value={periodScope}
                onChange={(event) => setPeriodScope(event.target.value)}
                style={{ fontSize: "var(--text-xs)", height: 24, padding: "1px 22px 1px 7px" }}
              >
                {PERIOD_SCOPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <Button
              variant="primary"
              size="xs"
              disabled={!exportAction.isDesktop || exportAction.isRunning}
              loading={exportAction.isRunning}
              onClick={() => exportAction.run()}
              style={{ width: "100%" }}
              >
                <SpreadsheetIcon />
                {exportAction.isRunning ? "Exporting" : "Export Excel"}
            </Button>
          </div>
        ) : null}
      </div>
      )}

      {downloadControls ? (
        <>
          <button
            type="button"
            className="focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan-600"
            aria-label="Choose custom history range"
            aria-expanded={showHistory}
            aria-controls={historyId}
            title="Choose custom history range"
            onClick={() => setShowHistory((value) => !value)}
            style={mappingWindowButtonStyle}
          >
            <OpenInWindowIcon />
          </button>
          <HistoryRangePopover
            id={historyId}
            open={showHistory}
            startYear={startYear}
            endYear={endYear}
            minYear={CVM_MIN_YEAR}
            maxYear={currentYear}
            hasError={Boolean(yearError)}
            error={yearError}
            disabled={historyDisabled}
            loading={pendingHistory}
            onStartYearChange={(value) => {
              setStartYear(value);
              setYearError(null);
            }}
            onEndYearChange={(value) => {
              setEndYear(value);
              setYearError(null);
            }}
            onDownload={() => {
              if (!validateYears()) return;
              setShowHistory(false);
              refreshMutation.mutate({ type: "history", startYear, endYear });
            }}
          />
        </>
      ) : null}

      {downloadControls && hasRefreshFeedback ? (
        <div style={feedbackPopoverStyle}>
          {isActive ? <ActiveProgress status={status} progress={progress} isFetching={statusQuery.isFetching} /> : null}
          {browserReason || statusQuery.isError || refreshMutation.isError || hasMarketRefreshFailure || marketRefreshResult || showDispatchNotice || showOutcomeNotice ? (
            <div className={isActive ? "mt-2" : undefined}>
              {browserReason ? <Notice tone="warning">{browserReason}</Notice> : null}
              {statusQuery.isError ? <ErrorNotice error={statusQuery.error} /> : null}
              {refreshMutation.isError ? <ErrorNotice error={refreshMutation.error} /> : null}
              {marketRefreshMutation.isError ? <ErrorNotice error={marketRefreshMutation.error} /> : null}
              {marketRefreshResult ? (
                <TransientNotice
                  noticeKey={`market-history:${marketRefreshResult.success_count}:${marketRefreshResult.failure_count}:${marketRefreshResult.attempted_count}`}
                  tone={marketRefreshResult.ok ? "success" : "warning"}
                >
                  {formatMarketHistoryRefreshMessage(marketRefreshResult)}
                </TransientNotice>
              ) : null}
              {showDispatchNotice && refreshMutation.data ? <DispatchNotice result={refreshMutation.data} /> : null}
              {showOutcomeNotice ? (
                <TransientNotice noticeKey={`${dispatchJobId}:${refreshState}`} tone="success">
                  {formatRefreshSuccessMessage(status)}
                </TransientNotice>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {!downloadControls && isActive ? <ActiveProgress status={status} progress={progress} isFetching={statusQuery.isFetching} /> : null}

      {!downloadControls && (browserReason || statusQuery.isError || refreshMutation.isError || hasMarketRefreshFailure || marketRefreshResult || showDispatchNotice || showOutcomeNotice) ? (
        <div className="mt-2">
          {browserReason ? <Notice tone="warning">{browserReason}</Notice> : null}
          {statusQuery.isError ? <ErrorNotice error={statusQuery.error} /> : null}
          {refreshMutation.isError ? <ErrorNotice error={refreshMutation.error} /> : null}
          {marketRefreshMutation.isError ? <ErrorNotice error={marketRefreshMutation.error} /> : null}
          {marketRefreshResult ? (
            <TransientNotice
              noticeKey={`market-history:${marketRefreshResult.success_count}:${marketRefreshResult.failure_count}:${marketRefreshResult.attempted_count}`}
              tone={marketRefreshResult.ok ? "success" : "warning"}
            >
              {formatMarketHistoryRefreshMessage(marketRefreshResult)}
            </TransientNotice>
          ) : null}
          {showDispatchNotice && refreshMutation.data ? <DispatchNotice result={refreshMutation.data} /> : null}
          {showOutcomeNotice ? (
            <TransientNotice noticeKey={`${dispatchJobId}:${refreshState}`} tone="success">
              {formatRefreshSuccessMessage(status)}
            </TransientNotice>
          ) : null}
        </div>
      ) : null}

      {showHistory && !downloadControls ? (
        <div id={historyId} className="mt-2" style={disclosureStyle}>
          <div className="flex flex-wrap items-end gap-2">
            {(["3y", "5y", "10y", "full"] as const).map((preset) => (
              <PresetButton key={preset} onSelect={() => applyPreset(preset)}>
                {preset === "full" ? "Full history" : `Last ${preset === "3y" ? 3 : preset === "5y" ? 5 : 10} years`}
              </PresetButton>
            ))}
            <YearInput
              id={`command-start-year-${cdCvm}`}
              label="Start year"
              value={startYear}
              min={CVM_MIN_YEAR}
              max={currentYear}
              hasError={Boolean(yearError)}
              onChange={(value) => {
                setStartYear(value);
                setYearError(null);
              }}
            />
            <YearInput
              id={`command-end-year-${cdCvm}`}
              label="End year"
              value={endYear}
              min={CVM_MIN_YEAR}
              max={currentYear}
              hasError={Boolean(yearError)}
              onChange={(value) => {
                setEndYear(value);
                setYearError(null);
              }}
            />
            <Button
              variant="secondary"
              size="xs"
              disabled={updateDisabled}
              loading={pendingHistory}
              onClick={downloadHistory}
            >
              {pendingHistory ? `Downloading ${startYear}-${endYear}...` : "Download selected history"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              aria-expanded={showDetails}
              aria-controls={detailsId}
              onClick={() => setShowDetails((value) => !value)}
            >
              {COMPANY_COMMAND_LABELS.refreshDetails}
            </Button>
          </div>
          {yearError ? <p role="alert" style={errorTextStyle}>{yearError}</p> : null}
          {showDetails ? (
            <div id={detailsId} className="mt-2">
              <StatusDetails status={status} loading={refreshState === "loading"} isFetching={statusQuery.isFetching} />
            </div>
          ) : null}
        </div>
      ) : null}

      {!hideExport && exportAction.status === "success" ? (
        <div className="mt-2">
          <TransientNotice noticeKey={`export:${exportAction.lastRunAt?.getTime() ?? 0}`} tone="success">
            {`Workbook exported${exportAction.result?.file_name ? `: ${exportAction.result.file_name}` : "."}`}
          </TransientNotice>
        </div>
      ) : !hideExport && exportAction.status === "error" ? (
        <div className="mt-2"><Notice tone="error" role="alert">{exportAction.errorMessage ?? "Export failed."}</Notice></div>
      ) : null}
    </section>
  );
}

export function companyDataInvalidationKeys(cdCvm: number): QueryKey[] {
  return [
    ["company-info", cdCvm],
    ["company-years", cdCvm],
    ["company-statement-years", cdCvm],
    ["company-kpis"],
    ["company-statement"],
    ["companies"],
    ["data-coverage"],
    ["db-diagnostics"],
    ["base-health"],
    ["refresh-jobs"],
    ["company-refresh-status"],
    ["company-financial-readiness", cdCvm],
    ["market-history", cdCvm],
    ["market-history-status", cdCvm],
  ];
}

function invalidateMarketHistoryData(queryClient: QueryClient, cdCvm: number) {
  for (const queryKey of [["market-history", cdCvm], ["market-history-status", cdCvm]] as QueryKey[]) {
    void queryClient.invalidateQueries({ queryKey });
  }
}

function CommandLink({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}) {
  return (
    <Link
      to={to}
      style={{
        alignItems: "center",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-md)",
        color: "var(--color-text-primary)",
        display: "inline-flex",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-xs)",
        fontWeight: 500,
        gap: 6,
        height: 22,
        justifyContent: "center",
        padding: "2px 8px",
        textDecoration: "none",
      }}
    >
      {children}
    </Link>
  );
}

function invalidateCompanyData(queryClient: QueryClient, cdCvm: number) {
  for (const queryKey of companyDataInvalidationKeys(cdCvm)) {
    void queryClient.invalidateQueries({ queryKey });
  }
}

function StatusDetails({
  status,
  loading,
  isFetching,
}: {
  status: CompanyRefreshStatus | null;
  loading: boolean;
  isFetching: boolean;
}) {
  if (loading) return <Notice tone="neutral">Loading refresh diagnostics...</Notice>;
  if (!status) return <Notice tone="neutral">No technical refresh details are available yet.</Notice>;
  const progress = companyRefreshProgress(status);
  const state = normalizedTrackingState(status);
  const reason =
    status.latest_attempt_reason_message ||
    status.status_reason_message ||
    (state === "no_data" ? status.progress_message : null);
  return (
    <div className="space-y-2">
      <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Last refresh" value={formatDateTime(status.last_success_at ?? null)} />
        <Field label="Last attempt" value={formatDateTime(status.last_attempt_at ?? null)} />
        <Field label="Rows inserted" value={formatNullable(status.last_rows_inserted)} />
        <Field label="Range" value={formatRange(status)} />
        <Field label="Source" value={status.source_label || status.source_scope || "n/a"} />
        <Field label="Job" value={shortJobId(status.job_id)} mono />
        <Field label="State" value={formatStateLabel(state)} />
        <Field label="Progress" value={progress == null ? "n/a" : `${progress}%`} mono />
      </dl>
      {isFetching && isActiveCompanyRefresh(status) ? <Notice tone="warning">Polling active refresh status...</Notice> : null}
      {reason ? <Notice tone={state === "no_data" ? "warning" : "neutral"}>{reason}</Notice> : null}
      {status.last_error ? <Notice tone="error">{status.last_error}</Notice> : null}
    </div>
  );
}

function SpreadsheetIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3.5 1.75h6l3 3v9.5H3.5z" />
      <path d="M9.5 1.75v3h3" />
      <path d="M5.5 7.25h5M5.5 9.5h5M7.25 7.25v4.5" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 2.5v7" />
      <path d="m5.25 6.75 2.75 2.75 2.75-2.75" />
      <path d="M3 12.75h10" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M13 7a5 5 0 0 0-8.7-2.9L3 5.5" />
      <path d="M3 2.75V5.5h2.75" />
      <path d="M3 9a5 5 0 0 0 8.7 2.9L13 10.5" />
      <path d="M13 13.25V10.5h-2.75" />
    </svg>
  );
}

function OpenInWindowIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 4v8H4" />
    </svg>
  );
}

function ActiveProgress({
  status,
  progress,
  isFetching,
}: {
  status: CompanyRefreshStatus | null;
  progress: number | null;
  isFetching: boolean;
}) {
  return (
    <div className="mt-2">
      <div
        className="mb-1 flex justify-between gap-3 font-mono"
        style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}
      >
        <span>{status?.progress_message || formatStage(status?.stage)}{isFetching ? " · polling" : ""}</span>
        <span>{progress == null ? "working" : `${progress}%`}</span>
      </div>
      <div className="h-1 overflow-hidden" style={{ background: "var(--color-surface-3)", borderRadius: "var(--radius-sm)" }}>
        <div className="h-full transition-all" style={{ background: "var(--color-id-ticker)", width: `${progress ?? 35}%` }} />
      </div>
    </div>
  );
}

function PresetButton({ children, onSelect }: { children: ReactNode; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect} style={presetButtonStyle}>
      {children}
    </button>
  );
}

function YearInput({
  id,
  label,
  value,
  min,
  max,
  hasError,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  hasError: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div style={{ minWidth: 104 }}>
      <label htmlFor={id} style={{ color: "var(--color-text-tertiary)", display: "block", fontSize: "var(--text-2xs)", marginBottom: 2 }}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number.parseInt(event.target.value, 10))}
        style={{
          background: "var(--color-surface-2)",
          border: `1px solid ${hasError ? "var(--color-state-err)" : "var(--color-border-default)"}`,
          borderRadius: "var(--radius-sm)",
          color: "var(--color-text-primary)",
          fontSize: "var(--text-xs)",
          height: 22,
          padding: "2px 7px",
          width: "100%",
        }}
      />
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)", textTransform: "uppercase" }}>
        {label}
      </dt>
      <dd className={mono ? "mt-0.5 font-mono" : "mt-0.5"} style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)", marginLeft: 0 }}>
        {value}
      </dd>
    </div>
  );
}

type NoticeTone = "neutral" | "success" | "warning" | "error";

function Notice({ tone, role, children }: { tone: NoticeTone; role?: "alert" | "status"; children: ReactNode }) {
  return <p role={role} style={noticeStyle(tone)}>{children}</p>;
}

function ErrorNotice({ error }: { error: unknown }) {
  return <Notice tone="error" role="alert">{error instanceof Error ? error.message : String(error)}</Notice>;
}

function DispatchNotice({ result }: { result: RefreshDispatchResponse }) {
  const ok = result.status !== "error";
  return (
    <Notice tone={ok ? "success" : "error"} role={ok ? "status" : "alert"}>
      {result.message || formatStateLabel(result.status)}
      {result.job_id ? <span className="ml-2 font-mono text-xs opacity-80">{shortJobId(result.job_id)}</span> : null}
    </Notice>
  );
}

export function shouldShowRefreshOutcome(
  dispatchJobId: string | null,
  statusJobId: string | null,
  refreshState: string,
): boolean {
  return Boolean(dispatchJobId) && dispatchJobId === statusJobId && refreshState === "success";
}

function formatRefreshSuccessMessage(status: CompanyRefreshStatus | null): string {
  const message = String(status?.progress_message || "").trim();
  if (!message) return "Update completed.";
  if (/^refresh conclu[ií]do/i.test(message)) {
    const range = message.match(/(\d{4})\s*(?:-|–|a)\s*(\d{4})/i);
    return range ? `Refresh completed. Local data is ready for ${range[1]}–${range[2]}.` : "Refresh completed. Local data is ready.";
  }
  return message;
}

function formatMarketHistoryRefreshMessage(result: CompanyMarketHistoryAllRefreshResult): string {
  if (result.attempted_count === 0) {
    return "Market history was not updated: no ticker is available.";
  }
  if (result.failure_count === 0) {
    return `Market history updated for ${result.success_count} ticker${result.success_count === 1 ? "" : "s"}.`;
  }
  return `Market history updated for ${result.success_count} of ${result.attempted_count} tickers; ${result.failure_count} failed.`;
}

function TransientNotice({
  noticeKey,
  tone,
  children,
}: {
  noticeKey: string;
  tone: "success" | "warning";
  children: ReactNode;
}) {
  const [visible, setVisible] = useState(true);
  const [entered, setEntered] = useState(false);
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    setVisible(true);
    setEntered(false);
    setLeaving(false);
    const enterFrame = window.requestAnimationFrame(() => setEntered(true));
    const leaveTimer = window.setTimeout(() => setLeaving(true), 5_500);
    const removeTimer = window.setTimeout(() => setVisible(false), 5_700);
    return () => {
      window.cancelAnimationFrame(enterFrame);
      window.clearTimeout(leaveTimer);
      window.clearTimeout(removeTimer);
    };
  }, [noticeKey]);
  if (!visible) return null;
  return (
    <div
      style={{
        maxHeight: leaving ? 0 : 48,
        opacity: entered && !leaving ? 1 : 0,
        overflow: "hidden",
        transform: entered && !leaving ? "translateY(0)" : "translateY(-4px)",
        transition: "max-height 180ms ease, opacity 180ms ease, transform 180ms ease",
      }}
    >
      <Notice tone={tone} role="status">{children}</Notice>
    </div>
  );
}

function HistoryRangePopover({
  id,
  open,
  startYear,
  endYear,
  minYear,
  maxYear,
  hasError,
  error,
  disabled,
  loading,
  onStartYearChange,
  onEndYearChange,
  onDownload,
}: {
  id: string;
  open: boolean;
  startYear: number;
  endYear: number;
  minYear: number;
  maxYear: number;
  hasError: boolean;
  error: string | null;
  disabled: boolean;
  loading: boolean;
  onStartYearChange: (value: number) => void;
  onEndYearChange: (value: number) => void;
  onDownload: () => void;
}) {
  const [mounted, setMounted] = useState(open);
  const [entered, setEntered] = useState(open);

  useEffect(() => {
    if (open) {
      setMounted(true);
      const frame = window.requestAnimationFrame(() => setEntered(true));
      return () => window.cancelAnimationFrame(frame);
    }
    setEntered(false);
    const timer = window.setTimeout(() => setMounted(false), 180);
    return () => window.clearTimeout(timer);
  }, [open]);

  if (!mounted) return null;
  return (
    <div
      id={id}
      role="dialog"
      aria-label="Custom history range"
      aria-hidden={!open}
      style={{
        ...historyPopoverStyle,
        opacity: entered ? 1 : 0,
        pointerEvents: entered ? "auto" : "none",
        transform: entered ? "translateY(0)" : "translateY(-4px)",
      }}
    >
      <span style={popoverLabelStyle}>Custom CVM history range</span>
      <div className="mt-2 flex gap-2">
        <YearInput
          id={`${id}-start-year`}
          label="Start year"
          value={startYear}
          min={minYear}
          max={maxYear}
          hasError={hasError}
          onChange={onStartYearChange}
        />
        <YearInput
          id={`${id}-end-year`}
          label="End year"
          value={endYear}
          min={minYear}
          max={maxYear}
          hasError={hasError}
          onChange={onEndYearChange}
        />
      </div>
      {error ? <p role="alert" style={errorTextStyle}>{error}</p> : null}
      <Button
        variant="primary"
        size="xs"
        disabled={disabled}
        loading={loading}
        onClick={onDownload}
        style={{ marginTop: 10, width: "100%" }}
      >
        {loading ? "Downloading" : "Download selected range"}
      </Button>
    </div>
  );
}

function barStyle(needsAttention: boolean, flat: boolean): CSSProperties {
  if (flat) {
    return {
      background: "transparent",
      border: "none",
      borderRadius: 0,
      padding: 0,
    };
  }
  return {
    background: "var(--color-surface-2)",
    border: `1px solid ${needsAttention ? "var(--color-state-warn)" : "var(--color-border-subtle)"}`,
    borderRadius: "var(--radius-md)",
    padding: "13px 12px",
  };
}

const disclosureStyle: CSSProperties = {
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
  padding: 8,
};

export const historyPopoverStyle: CSSProperties = {
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-default)",
  borderRadius: "var(--radius-md)",
  boxShadow: "0 10px 24px rgb(0 0 0 / 0.28)",
  padding: 10,
  position: "absolute",
  right: 0,
  top: "calc(100% + 8px)",
  transition: "opacity 180ms ease, transform 180ms ease",
  width: 284,
  zIndex: 10,
};

const feedbackPopoverStyle: CSSProperties = {
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-default)",
  borderRadius: "var(--radius-md)",
  boxShadow: "0 10px 24px rgb(0 0 0 / 0.28)",
  padding: 8,
  position: "absolute",
  right: 0,
  top: "calc(100% + 8px)",
  width: "min(360px, 100%)",
  zIndex: 10,
};

const popoverLabelStyle: CSSProperties = {
  color: "var(--color-text-tertiary)",
  fontSize: "var(--text-2xs)",
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const mappingWindowButtonStyle: CSSProperties = {
  alignItems: "center",
  background: "transparent",
  border: "none",
  bottom: 2,
  color: "var(--color-text-secondary)",
  cursor: "pointer",
  display: "inline-flex",
  height: 22,
  justifyContent: "center",
  padding: 0,
  position: "absolute",
  right: 2,
  width: 22,
};

const presetButtonStyle: CSSProperties = {
  background: "var(--color-surface-2)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
  color: "var(--color-text-secondary)",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
  height: 22,
  padding: "2px 7px",
};

const errorTextStyle: CSSProperties = {
  color: "var(--color-state-err)",
  fontSize: "var(--text-xs)",
  margin: "7px 0 0",
};

function noticeStyle(tone: NoticeTone): CSSProperties {
  const color =
    tone === "success"
      ? "var(--color-state-ok)"
      : tone === "warning"
        ? "var(--color-state-warn)"
        : tone === "error"
          ? "var(--color-state-err)"
          : "var(--color-text-secondary)";
  return {
    background: "var(--color-surface-1)",
    border: `1px solid ${tone === "neutral" ? "var(--color-border-subtle)" : color}`,
    borderRadius: "var(--radius-sm)",
    color,
    fontSize: "var(--text-xs)",
    margin: 0,
    padding: "6px 8px",
  };
}

function formatStateLabel(value: string | null | undefined): string {
  const normalized = String(value || "idle");
  if (normalized === "no_data") return "No data";
  if (normalized === "already_current") return "Already current";
  if (normalized === "success") return "Up to date";
  return normalized.replace(/_/g, " ");
}

function formatStage(value: string | null | undefined): string {
  return value ? value.replace(/_/g, " ") : "Progress";
}

function formatNullable(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  return value;
}

function formatRange(status: CompanyRefreshStatus): string {
  if (status.last_start_year == null && status.last_end_year == null) return "n/a";
  return `${status.last_start_year ?? "?"}-${status.last_end_year ?? "?"}`;
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

function shortJobId(value: string | null | undefined): string {
  if (!value) return "n/a";
  return value.length > 12 ? `${value.slice(0, 8)}...` : value;
}
