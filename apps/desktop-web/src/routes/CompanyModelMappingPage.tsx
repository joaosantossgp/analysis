import { Fragment, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { useExportAction } from "@/components/export/useExportAction";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import {
  fetchExcelMappingWorkspace,
  saveExcelMappingPreset,
  setCompanyExcelMappingDefault,
  type ExcelMappingWorkspaceResult,
} from "@/lib/api/excelMappings";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type {
  ExcelMappingDefinition,
  ExcelMappingEntry,
  ExcelMappingPreviewRow,
  ExcelMappingRawLine,
  ExcelMappingSource,
  ExcelMappingValidationIssue,
} from "@/lib/bridge/types";

const SYSTEM_DEFAULT_PRESET_ID = "system:default";
const OPERATIONS = [
  { value: "direct", label: "Direct" },
  { value: "sum", label: "Sum" },
  { value: "sum_with_sign", label: "Signed Sum" },
] as const;
const PERIOD_SCOPE_OPTIONS = [
  { value: "last_3_years", label: "Last 3 years" },
  { value: "last_5_years", label: "Last 5 years" },
  { value: "last_10_years", label: "Last 10 years" },
  { value: "full_history", label: "Full history" },
] as const;
const STATEMENT_LABELS: Record<string, string> = {
  DRE: "Income Statement",
  BPA: "Balance Sheet Assets",
  BPP: "Liabilities & Equity",
  DFC: "Cash Flow",
  DMPL: "Changes in Equity",
};
const STATEMENT_DESCRIPTIONS: Record<string, string> = {
  DRE: "Revenue, costs, margins, and earnings",
  BPA: "Asset accounts mapped into the model",
  BPP: "Liability and equity accounts",
  DFC: "Cash flow accounts and subtotal lines",
  DMPL: "Equity movement accounts",
};
const STATEMENT_ORDER = ["DRE", "BPA", "BPP", "DFC", "DMPL"] as const;
const CORE_STATEMENT_TYPES = ["DRE", "BPA", "BPP", "DFC"] as const;
const UNKNOWN_STATEMENT_TYPE = "UNKNOWN";

type PreviewRow = ExcelMappingPreviewRow & {
  rowIssues: ExcelMappingValidationIssue[];
  edited: boolean;
};
type StatementGroupSummary = {
  statementType: string;
  label: string;
  description: string;
  rows: PreviewRow[];
  rowCount: number;
  mappedCount: number;
  sourceCount: number;
  warningCount: number;
  errorCount: number;
  editedCount: number;
  rowIds: string;
};

export function CompanyModelMappingPage() {
  const params = useParams<{ cdCvm: string }>();
  const cdCvm = Number.parseInt(params.cdCvm ?? "", 10);
  const queryClient = useQueryClient();
  const [periodScope, setPeriodScope] = useState("last_5_years");
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ExcelMappingDefinition | null>(null);
  const [selectedTargetId, setSelectedTargetId] = useState<string | null>(null);
  const [presetName, setPresetName] = useState("");
  const [presetDescription, setPresetDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [rawSearch, setRawSearch] = useState("");
  const [rawStatementFilter, setRawStatementFilter] = useState("current");
  const [showValidation, setShowValidation] = useState(false);
  const [activeStatementType, setActiveStatementType] = useState<string>("DRE");
  const [bridgeReady, setBridgeReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const workspaceQuery = useQuery<ExcelMappingWorkspaceResult>({
    queryKey: ["excel-mapping-workspace", cdCvm, selectedPresetId, periodScope],
    queryFn: () => fetchExcelMappingWorkspace(cdCvm, selectedPresetId, periodScope),
    enabled: bridgeReady && Number.isFinite(cdCvm) && cdCvm > 0,
  });

  const workspace =
    workspaceQuery.data?.mode === "desktop" ? workspaceQuery.data.workspace : null;

  useEffect(() => {
    if (!workspace?.mapping) return;
    const shouldPreserveDraft =
      touched && draft?.preset_id === workspace.mapping.preset_id;
    setSelectedPresetId(workspace.active_preset_id);
    if (shouldPreserveDraft) return;
    setDraft(workspace.mapping);
    setSelectedTargetId((current) => (
      current && workspace.mapping.entries.some((entry) => entry.target_id === current)
        ? current
        : workspace.mapping.entries[0]?.target_id ?? null
    ));
    setPresetName(workspace.mapping.origin === "system" ? "" : workspace.mapping.name);
    setPresetDescription(workspace.mapping.description ?? "");
    setTouched(false);
  }, [draft?.preset_id, touched, workspace]);

  const validation = useMemo(
    () => mergeValidationIssues(
      workspace?.validation ?? [],
      draft && workspace ? validateDraft(draft, workspace.raw_lines) : [],
    ),
    [draft, workspace],
  );
  const blockingCount = validation.filter((issue) => issue.severity === "error").length;
  const warningCount = validation.filter((issue) => issue.severity !== "error").length;

  const previewRows = useMemo(
    () => buildPreviewRows(draft, workspace, validation),
    [draft, validation, workspace],
  );
  const statementGroups = useMemo(
    () => buildStatementGroups(previewRows),
    [previewRows],
  );
  const activeStatementGroup = useMemo(
    () => {
      const fallback = statementGroups.find((group) => group.rowCount > 0)
        ?? statementGroups[0]
        ?? null;
      return statementGroups.find((group) => group.statementType === activeStatementType)
        ?? fallback;
    },
    [activeStatementType, statementGroups],
  );
  useEffect(() => {
    if (statementGroups.length === 0) return;
    if (statementGroups.some((group) => group.statementType === activeStatementType)) return;
    const nextStatement = statementGroups.find((group) => group.rowCount > 0)?.statementType
      ?? statementGroups[0]?.statementType;
    if (nextStatement) setActiveStatementType(nextStatement);
  }, [activeStatementType, statementGroups]);
  useEffect(() => {
    if (!activeStatementGroup) return;
    const selectedStillVisible = Boolean(
      selectedTargetId
        && activeStatementGroup.rows.some((row) => row.target_id === selectedTargetId),
    );
    if (selectedStillVisible) return;
    setSelectedTargetId(activeStatementGroup.rows[0]?.target_id ?? null);
  }, [activeStatementGroup, selectedTargetId]);
  const selectedEntry = useMemo(
    () => {
      if (!draft || !selectedTargetId) return null;
      if (
        activeStatementGroup
        && !activeStatementGroup.rows.some((row) => row.target_id === selectedTargetId)
      ) {
        return null;
      }
      return draft.entries.find((entry) => entry.target_id === selectedTargetId) ?? null;
    },
    [activeStatementGroup, draft, selectedTargetId],
  );
  const selectedPreviewRow = useMemo(
    () => previewRows.find((row) => row.target_id === selectedEntry?.target_id) ?? null,
    [previewRows, selectedEntry],
  );
  const exportPresetId =
    draft?.origin === "system" ? undefined : draft?.preset_id;
  const exportAction = useExportAction({
    cdCvm,
    periodScope,
    mappingPresetId: exportPresetId,
  });

  const saveMutation = useMutation({
    mutationFn: saveExcelMappingPreset,
    onSuccess: async (saved) => {
      setSelectedPresetId(saved.preset_id);
      setTouched(false);
      await queryClient.invalidateQueries({ queryKey: ["excel-mapping-workspace", cdCvm] });
    },
  });
  const defaultMutation = useMutation({
    mutationFn: (presetId: string) => setCompanyExcelMappingDefault(cdCvm, presetId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["excel-mapping-workspace", cdCvm] });
    },
  });

  function updateEntry(targetId: string, updater: (entry: ExcelMappingEntry) => ExcelMappingEntry) {
    setDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        entries: current.entries.map((entry) => (
          entry.target_id === targetId ? updater(entry) : entry
        )),
      };
    });
    setTouched(true);
  }

  function saveDraft({ asNew = false }: { asNew?: boolean } = {}) {
    if (!workspace || !draft) return;
    const name = presetName.trim() || `Custom - ${workspace.company.ticker_b3 ?? cdCvm}`;
    const mapping: ExcelMappingDefinition = {
      ...draft,
      preset_id: asNew || draft.origin === "system" ? "" : draft.preset_id,
      name,
      description: presetDescription.trim() || null,
      origin: "user",
    };
    saveMutation.mutate(mapping);
  }

  function resetToDefault() {
    setSelectedPresetId(SYSTEM_DEFAULT_PRESET_ID);
    setPickerOpen(false);
    setRawSearch("");
    if (workspace?.active_preset_id === SYSTEM_DEFAULT_PRESET_ID) {
      setDraft(workspace.mapping);
      setSelectedTargetId(workspace.mapping.entries[0]?.target_id ?? null);
      setPresetName("");
      setPresetDescription(workspace.mapping.description ?? "");
    }
    setTouched(false);
  }

  function addSource(line: ExcelMappingRawLine, sign: 1 | -1) {
    if (!selectedEntry) return;
    updateEntry(selectedEntry.target_id, (entry) => {
      const exists = entry.sources.some(
        (source) => source.statement_type === line.statement_type
          && source.line_id_base === line.line_id_base,
      );
      if (exists) return entry;
      const source: ExcelMappingSource = {
        statement_type: line.statement_type,
        line_id_base: line.line_id_base,
        cd_conta: line.cd_conta,
        label_snapshot: line.standard_name ?? line.ds_conta ?? line.label,
        sign,
        position: entry.sources.length,
      };
      const sources = [...entry.sources, source];
      return {
        ...entry,
        operation: sign < 0 || sources.some((item) => item.sign < 0)
          ? "sum_with_sign"
          : sources.length > 1 ? "sum" : entry.operation,
        sources,
      };
    });
  }

  function removeSource(sourceIndex: number) {
    if (!selectedEntry) return;
    updateEntry(selectedEntry.target_id, (entry) => ({
      ...entry,
      sources: entry.sources
        .filter((_, index) => index !== sourceIndex)
        .map((source, position) => ({ ...source, position })),
    }));
  }

  function setSourceSign(sourceIndex: number, sign: number) {
    if (!selectedEntry) return;
    updateEntry(selectedEntry.target_id, (entry) => ({
      ...entry,
      operation: "sum_with_sign",
      sources: entry.sources.map((source, index) => (
        index === sourceIndex ? { ...source, sign } : source
      )),
    }));
  }

  if (!Number.isFinite(cdCvm) || cdCvm <= 0) {
    return <StateBanner variant="error" title="Invalid CVM code" />;
  }
  if (!bridgeReady || workspaceQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading model builder..." />;
  }
  if (workspaceQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Could not load Model Export Builder"
        message={workspaceQuery.error instanceof Error ? workspaceQuery.error.message : String(workspaceQuery.error)}
        onRetry={() => workspaceQuery.refetch()}
      />
    );
  }
  if (workspaceQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={workspaceQuery.data.reason} />;
  }
  if (!workspace || !draft) {
    return <StateBanner variant="empty" title="No mapping workspace available" />;
  }

  return (
    <section className="space-y-4">
      <BuilderCommandBar
        companyName={workspace.company.company_name}
        ticker={workspace.company.ticker_b3}
        cdCvm={cdCvm}
        draft={draft}
        presets={workspace.presets}
        selectedPresetId={workspace.active_preset_id}
        periodScope={periodScope}
        presetName={presetName}
        presetDescription={presetDescription}
        touched={touched}
        blockingCount={blockingCount}
        warningCount={warningCount}
        latestPeriod={workspace.company.latest_financial_period_display}
        periodScopeLabel={workspace.period_scope_label ?? null}
        exportStatus={exportAction.status}
        exportError={exportAction.errorMessage}
        exportFile={exportAction.result?.file_name ?? null}
        onPresetChange={(presetId) => {
          setSelectedPresetId(presetId);
          setTouched(false);
          setPickerOpen(false);
        }}
        onPeriodScopeChange={setPeriodScope}
        onNameChange={(value) => {
          setPresetName(value);
          setTouched(true);
        }}
        onDescriptionChange={(value) => {
          setPresetDescription(value);
          setTouched(true);
        }}
        onSave={() => saveDraft()}
        onSaveAs={() => saveDraft({ asNew: true })}
        onReset={resetToDefault}
        onSetCompanyDefault={() => defaultMutation.mutate(draft.preset_id)}
        onExport={() => exportAction.run()}
        saving={saveMutation.isPending}
        settingDefault={defaultMutation.isPending}
        exporting={exportAction.isRunning}
        exportDisabled={!exportAction.isDesktop || exportAction.isRunning}
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-3">
          <StatementMappingSelector
            groups={statementGroups}
            activeStatementType={activeStatementGroup?.statementType ?? activeStatementType}
            onChange={setActiveStatementType}
          />
          <ModelPreviewTable
            periods={workspace.preview_periods}
            rows={activeStatementGroup?.rows ?? []}
            statement={activeStatementGroup}
            selectedTargetId={selectedEntry?.target_id ?? null}
            onSelectRow={setSelectedTargetId}
          />
          <ValidationStrip
            validation={validation}
            entries={draft.entries}
            blockingCount={blockingCount}
            warningCount={warningCount}
            showDetails={showValidation}
            onToggle={() => setShowValidation((value) => !value)}
            touched={touched}
          />
        </div>
        <RowInspector
          entry={selectedEntry}
          previewRow={selectedPreviewRow}
          periods={workspace.preview_periods}
          validation={validation}
          touched={touched}
          onOpenPicker={() => setPickerOpen(true)}
          onOperationChange={(operation) => {
            if (!selectedEntry) return;
            updateEntry(selectedEntry.target_id, (entry) => ({ ...entry, operation }));
          }}
          onRemoveSource={removeSource}
          onSourceSignChange={setSourceSign}
        />
      </div>
      {pickerOpen ? (
        <RawSourcePicker
          entry={selectedEntry}
          periods={workspace.preview_periods}
          rawLines={workspace.raw_lines}
          search={rawSearch}
          statementFilter={rawStatementFilter}
          onSearchChange={setRawSearch}
          onStatementFilterChange={setRawStatementFilter}
          onAddSource={addSource}
          onClose={() => setPickerOpen(false)}
        />
      ) : null}
      {saveMutation.isError ? (
        <StateBanner
          variant="error"
          title="Could not save preset"
          message={saveMutation.error instanceof Error ? saveMutation.error.message : String(saveMutation.error)}
        />
      ) : null}
      {defaultMutation.isError ? (
        <StateBanner
          variant="error"
          title="Could not set company default"
          message={defaultMutation.error instanceof Error ? defaultMutation.error.message : String(defaultMutation.error)}
        />
      ) : null}
    </section>
  );
}

function StatementMappingSelector({
  groups,
  activeStatementType,
  onChange,
}: {
  groups: StatementGroupSummary[];
  activeStatementType: string;
  onChange: (statementType: string) => void;
}) {
  return (
    <Panel dense title="Statement" subtitle="Model mapping family">
      <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-4">
        {groups.map((group) => {
          const selected = group.statementType === activeStatementType;
          const hasIssues = group.errorCount > 0 || group.warningCount > 0;
          return (
            <button
              key={group.statementType}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(group.statementType)}
              className="text-left focus-visible:outline focus-visible:outline-1"
              style={{
                background: selected ? "var(--color-surface-3)" : "var(--color-surface-1)",
                border: `1px solid ${
                  selected ? "var(--color-action-primary)" : "var(--color-border-default)"
                }`,
                borderRadius: "var(--radius-sm)",
                color: selected ? "var(--color-action-primary)" : "var(--color-text-primary)",
                minHeight: 74,
                outlineColor: "var(--color-border-focus)",
                padding: "8px 10px",
              }}
            >
              <span className="flex items-center justify-between gap-2">
                <span className="font-mono" style={{ fontSize: "var(--text-sm)" }}>
                  {group.statementType}
                </span>
                <span style={{ color: selected ? "var(--color-action-primary)" : "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>
                  {group.rowCount} rows
                </span>
              </span>
              <span className="mt-1 block truncate" style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)", fontWeight: 650 }}>
                {group.label}
              </span>
              <span className="mt-0.5 block truncate" style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>
                {group.description}
              </span>
              <span className="mt-2 flex flex-wrap gap-1.5">
                <MiniBadge tone={group.mappedCount > 0 ? "ok" : "warn"}>
                  {group.mappedCount} mapped
                </MiniBadge>
                {group.editedCount > 0 ? <MiniBadge tone="warn">{group.editedCount} edited</MiniBadge> : null}
                {group.errorCount > 0 ? <MiniBadge tone="error">{group.errorCount} error</MiniBadge> : null}
                {!group.errorCount && group.warningCount > 0 ? <MiniBadge tone="warn">{group.warningCount} warn</MiniBadge> : null}
                {!hasIssues ? <MiniBadge tone="ok">Clean</MiniBadge> : null}
              </span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function BuilderCommandBar({
  companyName,
  ticker,
  cdCvm,
  draft,
  presets,
  selectedPresetId,
  periodScope,
  presetName,
  presetDescription,
  touched,
  blockingCount,
  warningCount,
  latestPeriod,
  periodScopeLabel,
  exportStatus,
  exportError,
  exportFile,
  saving,
  settingDefault,
  exporting,
  exportDisabled,
  onPresetChange,
  onPeriodScopeChange,
  onNameChange,
  onDescriptionChange,
  onSave,
  onSaveAs,
  onReset,
  onSetCompanyDefault,
  onExport,
}: {
  companyName: string;
  ticker: string | null;
  cdCvm: number;
  draft: ExcelMappingDefinition;
  presets: Array<{ preset_id: string; name: string; origin: string; company_default: boolean }>;
  selectedPresetId: string;
  periodScope: string;
  presetName: string;
  presetDescription: string;
  touched: boolean;
  blockingCount: number;
  warningCount: number;
  latestPeriod: string | null;
  periodScopeLabel: string | null;
  exportStatus: string;
  exportError: string | null;
  exportFile: string | null;
  saving: boolean;
  settingDefault: boolean;
  exporting: boolean;
  exportDisabled: boolean;
  onPresetChange: (presetId: string) => void;
  onPeriodScopeChange: (scope: string) => void;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onSave: () => void;
  onSaveAs: () => void;
  onReset: () => void;
  onSetCompanyDefault: () => void;
  onExport: () => void;
}) {
  const isSystem = draft.origin === "system";
  const isCompanyDefault = presets.some(
    (preset) => preset.preset_id === selectedPresetId && preset.company_default,
  );
  return (
    <Panel
      dense
      title="Model Export Builder"
      subtitle="Preview the Excel Model sheet, audit source lines, then export a saved mapping."
    >
      <div className="grid gap-3 xl:grid-cols-[minmax(240px,0.8fr)_minmax(360px,1.2fr)_auto]">
        <div className="min-w-0">
          <div style={{ color: "var(--color-text-primary)", fontSize: "var(--text-md)", fontWeight: 650 }}>
            {ticker ?? `CVM ${cdCvm}`}
          </div>
          <div className="truncate" style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>
            {companyName}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <StatusChip tone="info">CVM {cdCvm}</StatusChip>
            <StatusChip tone={isSystem ? "muted" : "info"}>{isSystem ? "System Default" : "User Preset"}</StatusChip>
            <StatusChip tone={touched ? "warn" : "ok"}>{touched ? "Unsaved changes" : "Saved"}</StatusChip>
            {isCompanyDefault ? <StatusChip tone="ok">Company Default</StatusChip> : null}
            <StatusChip tone={blockingCount > 0 ? "error" : warningCount > 0 ? "warn" : "ok"}>
              {blockingCount > 0 ? `${blockingCount} errors` : warningCount > 0 ? `${warningCount} warnings` : "Validated"}
            </StatusChip>
            <StatusChip tone={latestPeriod ? "ok" : "warn"}>
              {latestPeriod ? `Updated through ${latestPeriod}` : "No complete period"}
            </StatusChip>
            {periodScopeLabel ? <StatusChip tone="muted">{periodScopeLabel}</StatusChip> : null}
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-[minmax(150px,0.7fr)_minmax(180px,1fr)_minmax(180px,1fr)]">
          <label style={labelStyle}>
            Active preset
            <Select
              value={selectedPresetId}
              onChange={(event) => onPresetChange(event.target.value)}
              style={controlStyle}
            >
              {presets.map((preset) => (
                <option key={preset.preset_id} value={preset.preset_id}>
                  {preset.name}{preset.company_default ? " (company default)" : ""}
                </option>
              ))}
            </Select>
          </label>
          <label style={labelStyle}>
            Save as name
            <input
              value={presetName}
              onChange={(event) => onNameChange(event.target.value)}
              placeholder="Distribution"
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            Notes
            <input
              value={presetDescription}
              onChange={(event) => onDescriptionChange(event.target.value)}
              placeholder="Preset notes"
              style={inputStyle}
            />
          </label>
        </div>
        <div className="flex min-w-[280px] flex-wrap items-end justify-end gap-2">
          <label style={{ ...labelStyle, minWidth: 130 }}>
            Period scope
            <Select
              value={periodScope}
              onChange={(event) => onPeriodScopeChange(event.target.value)}
              style={controlStyle}
            >
              {PERIOD_SCOPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </label>
          <Button size="xs" variant="secondary" onClick={onSave} disabled={blockingCount > 0 || saving} loading={saving}>
            Save
          </Button>
          <Button size="xs" variant="secondary" onClick={onSaveAs} disabled={blockingCount > 0 || saving}>
            Save As
          </Button>
          <Button size="xs" variant="ghost" onClick={onReset}>
            Reset
          </Button>
          <Button
            size="xs"
            variant="ghost"
            onClick={onSetCompanyDefault}
            disabled={isSystem || touched || settingDefault}
            loading={settingDefault}
          >
            Set Default
          </Button>
          <Button variant="primary" size="xs" onClick={onExport} disabled={exportDisabled} loading={exporting}>
            {exporting ? "Exporting" : "Export Excel"}
          </Button>
        </div>
      </div>
      <div className="mt-3" style={{ color: exportStatusColor(exportStatus), fontSize: "var(--text-xs)" }}>
        {touched
          ? "Unsaved draft changes are visible here but will not be included in export until you save the preset."
          : exportStatusMessage(exportStatus, exportError, exportFile)}
      </div>
    </Panel>
  );
}

function ModelPreviewTable({
  periods,
  rows,
  statement,
  selectedTargetId,
  onSelectRow,
}: {
  periods: string[];
  rows: PreviewRow[];
  statement: StatementGroupSummary | null;
  selectedTargetId: string | null;
  onSelectRow: (targetId: string) => void;
}) {
  const grouped = groupRows(rows);
  const statementLabel = statement?.label ?? "Statement";
  const statementType = statement?.statementType ?? "";
  const statementSummary = statement ? statementSummaryText(statement) : "No statement rows";
  return (
    <Panel
      dense
      title={`Model Preview: ${statementLabel}`}
      subtitle={`${statementType ? `${statementType} | ` : ""}${statementSummary}. R$ mm. Click a row to inspect source lines and export logic.`}
      footer="Values are previewed from local CVM data and scaled like the exported Excel Model sheet."
    >
      <div className="overflow-x-auto" style={tableFrameStyle}>
        <table className="w-full border-collapse" style={{ fontSize: "var(--text-xs)", minWidth: 880 }}>
          <thead>
            <tr style={tableHeaderRowStyle}>
              <th style={{ ...tableHeaderCellStyle, minWidth: 320, textAlign: "left" }}>Model row</th>
              <th style={{ ...tableHeaderCellStyle, minWidth: 120, textAlign: "left" }}>Source</th>
              {periods.map((period) => (
                <th key={period} style={tableHeaderCellStyle}>{period}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grouped.map((group) => (
              <Fragment key={group.name}>
                <tr style={{ background: "var(--color-surface-3)" }}>
                  <th colSpan={periods.length + 2} style={sectionRowStyle}>
                    {group.name}
                  </th>
                </tr>
                {group.rows.map((row) => {
                  const selected = row.target_id === selectedTargetId;
                  return (
                    <tr
                      key={row.target_id}
                      onClick={() => onSelectRow(row.target_id)}
                      style={{
                        background: selected ? "rgba(255, 122, 26, 0.08)" : "transparent",
                        borderBottom: "1px solid var(--color-border-subtle)",
                        cursor: "pointer",
                      }}
                    >
                      <th scope="row" style={{
                        ...modelRowHeaderStyle,
                        borderLeft: selected ? "2px solid var(--color-action-primary)" : "2px solid transparent",
                      }}>
                        <div style={{ paddingLeft: row.indent_level * 12 }}>
                          <span style={{ color: row.is_subtotal ? "var(--color-text-primary)" : "var(--color-text-secondary)", fontWeight: row.is_subtotal ? 650 : 500 }}>
                            {row.target_label}
                          </span>
                          <span className="ml-2 inline-flex gap-1 align-middle">
                            {row.edited ? <MiniBadge tone="warn">Edited</MiniBadge> : null}
                            {row.error_count > 0 ? <MiniBadge tone="error">{row.error_count} error</MiniBadge> : null}
                            {row.warning_count > 0 ? <MiniBadge tone="warn">{row.warning_count} warn</MiniBadge> : null}
                          </span>
                        </div>
                      </th>
                      <td style={sourceCellStyle}>
                        <MiniBadge tone={row.source_count > 0 ? "ok" : "warn"}>
                          {row.source_count} source{row.source_count === 1 ? "" : "s"}
                        </MiniBadge>
                      </td>
                      {periods.map((period) => (
                        <td key={period} style={valueCellStyle}>
                          {formatModelValue(row.values_by_period[period])}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </Fragment>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={periods.length + 2} style={{ color: "var(--color-text-tertiary)", padding: 24, textAlign: "center" }}>
                  No model rows are available for this statement in the active mapping.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function RowInspector({
  entry,
  previewRow,
  periods,
  validation,
  touched,
  onOpenPicker,
  onOperationChange,
  onRemoveSource,
  onSourceSignChange,
}: {
  entry: ExcelMappingEntry | null;
  previewRow: PreviewRow | null;
  periods: string[];
  validation: ExcelMappingValidationIssue[];
  touched: boolean;
  onOpenPicker: () => void;
  onOperationChange: (operation: string) => void;
  onRemoveSource: (index: number) => void;
  onSourceSignChange: (index: number, sign: number) => void;
}) {
  const entryIssues = entry
    ? validation.filter((issue) => issue.target_id === entry.target_id)
    : [];
  return (
    <Panel
      dense
      title={entry ? entry.target_label : "Selected Model Row"}
      subtitle={entry ? `${statementLabel(entry.statement_type)} | ${entry.required ? "Required" : "Optional"}` : "Click a row in the preview"}
      footer={touched ? "Save the preset before export if these draft changes should be used." : "Saved mapping is ready for export."}
    >
      {!entry ? (
        <p style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}>
          Select a Model row to inspect its CVM source lines.
        </p>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2">
            <MetricBox label="Sources" value={String(entry.sources.length)} tone={entry.sources.length ? "ok" : "warn"} />
            <MetricBox label="Latest preview" value={formatModelValue(latestPreviewValue(previewRow, periods))} tone="neutral" />
          </div>
          <label style={labelStyle}>
            Formula behavior
            <Select
              value={entry.operation}
              onChange={(event) => onOperationChange(event.target.value)}
              style={controlStyle}
            >
              {OPERATIONS.map((operation) => (
                <option key={operation.value} value={operation.value}>
                  {operation.label}
                </option>
              ))}
            </Select>
          </label>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div style={{ color: "var(--color-text-primary)", fontSize: "var(--text-sm)", fontWeight: 650 }}>
                CVM source lines
              </div>
              <Button size="xs" variant="secondary" onClick={onOpenPicker}>
                Add CVM Source
              </Button>
            </div>
            {entry.sources.map((source, index) => (
              <SourceLineCard
                key={`${source.statement_type}:${source.line_id_base}:${index}`}
                source={source}
                index={index}
                onRemove={onRemoveSource}
                onSignChange={onSourceSignChange}
              />
            ))}
            {entry.sources.length === 0 ? (
              <div style={emptyInsetStyle}>
                This row has no mapped CVM source line.
              </div>
            ) : null}
          </div>
          <div style={formulaBoxStyle}>
            <div style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)", fontWeight: 650 }}>
              Friendly formula
            </div>
            <div style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)", marginTop: 4 }}>
              {friendlyFormula(entry)}
            </div>
          </div>
          <details>
            <summary style={{ color: "var(--color-text-secondary)", cursor: "pointer", fontSize: "var(--text-xs)" }}>
              Advanced audit
            </summary>
            <div className="mt-2 space-y-1 font-mono" style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>
              <div>target: {entry.target_id}</div>
              <div>operation: {entry.operation}</div>
              <div>sources: {entry.sources.map((source) => `${source.statement_type}:${source.line_id_base}`).join(" + ") || "none"}</div>
              <div>Excel export: raw sheet links with /1000 scaling and IFERROR guard.</div>
            </div>
          </details>
          {entryIssues.length > 0 ? (
            <div className="space-y-1">
              <div style={{ color: "var(--color-state-warn)", fontSize: "var(--text-xs)", fontWeight: 650 }}>
                Row warnings
              </div>
              {entryIssues.slice(0, 5).map((issue) => (
                <div key={`${issue.code}:${issue.source_id ?? ""}:${issue.message}`} style={issueLineStyle(issue)}>
                  {friendlyIssueMessage(issue)}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  );
}

function RawSourcePicker({
  entry,
  periods,
  rawLines,
  search,
  statementFilter,
  onSearchChange,
  onStatementFilterChange,
  onAddSource,
  onClose,
}: {
  entry: ExcelMappingEntry | null;
  periods: string[];
  rawLines: ExcelMappingRawLine[];
  search: string;
  statementFilter: string;
  onSearchChange: (value: string) => void;
  onStatementFilterChange: (value: string) => void;
  onAddSource: (line: ExcelMappingRawLine, sign: 1 | -1) => void;
  onClose: () => void;
}) {
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    const selectedStatement = statementFilter === "current" ? entry?.statement_type : statementFilter;
    return rawLines
      .filter((line) => !selectedStatement
        || selectedStatement === "all"
        || canonicalStatementType(line.statement_type) === canonicalStatementType(selectedStatement))
      .filter((line) => {
        if (!query) return true;
        return `${line.cd_conta ?? ""} ${line.line_id_base} ${line.label} ${line.ds_conta ?? ""} ${line.statement_type}`
          .toLowerCase()
          .includes(query);
      })
      .slice(0, 200);
  }, [entry, rawLines, search, statementFilter]);
  const statementOptions = useMemo(
    () => buildSourceStatementOptions(rawLines, entry),
    [entry, rawLines],
  );
  const selectedKeys = new Set(entry?.sources.map((source) => `${source.statement_type}:${source.line_id_base}`) ?? []);
  return (
    <div style={overlayStyle} role="dialog" aria-modal="true" aria-label="Add CVM source">
      <button type="button" aria-label="Close source picker" onClick={onClose} style={overlayBackdropStyle} />
      <aside style={drawerStyle}>
        <header style={drawerHeaderStyle}>
          <div>
            <h2 style={{ color: "var(--color-text-primary)", fontSize: "var(--text-lg)", fontWeight: 650, margin: 0 }}>
              Add CVM Source
            </h2>
            <p style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)", margin: "2px 0 0" }}>
              Search raw CVM lines and add them as positive or subtracting sources.
            </p>
          </div>
          <Button size="xs" variant="ghost" onClick={onClose}>Close</Button>
        </header>
        <div className="grid gap-2 md:grid-cols-[1fr_150px]" style={{ padding: 12 }}>
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search account code or label..."
            style={inputStyle}
          />
          <Select
            value={statementFilter}
            onChange={(event) => onStatementFilterChange(event.target.value)}
            style={controlStyle}
          >
            <option value="current">Current statement</option>
            <option value="all">All statements</option>
            {statementOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2 overflow-auto" style={{ maxHeight: "calc(100vh - 170px)", padding: "0 12px 12px" }}>
          {filtered.map((line) => {
            const key = `${line.statement_type}:${line.line_id_base}`;
            const alreadySelected = selectedKeys.has(key);
            const mappedElsewhere = (line.mapped_targets ?? []).some((target) => target.target_id !== entry?.target_id);
            return (
              <div key={key} style={rawLineStyle}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono" style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)" }}>
                      {line.statement_type} {line.cd_conta ?? line.line_id_base}
                    </span>
                    {mappedElsewhere ? <MiniBadge tone="warn">Mapped elsewhere</MiniBadge> : null}
                    {alreadySelected ? <MiniBadge tone="ok">Selected</MiniBadge> : null}
                  </div>
                  <div className="truncate" title={line.ds_conta ?? line.label} style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>
                    {line.standard_name ?? line.ds_conta ?? line.label}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 font-mono" style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>
                    <span>{line.periods_present.length} periods</span>
                    {periods.slice(-2).map((period) => (
                      <span key={period}>{period}: {formatModelValue(line.sample_values_by_period?.[period])}</span>
                    ))}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-1.5">
                  <Button size="xs" variant="secondary" disabled={alreadySelected || !entry} onClick={() => onAddSource(line, 1)}>
                    Include
                  </Button>
                  <Button size="xs" variant="ghost" disabled={alreadySelected || !entry} onClick={() => onAddSource(line, -1)}>
                    Subtract
                  </Button>
                </div>
              </div>
            );
          })}
          {filtered.length === 0 ? (
            <div style={emptyInsetStyle}>No raw CVM lines match this filter.</div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function SourceLineCard({
  source,
  index,
  onRemove,
  onSignChange,
}: {
  source: ExcelMappingSource;
  index: number;
  onRemove: (index: number) => void;
  onSignChange: (index: number, sign: number) => void;
}) {
  return (
    <div style={sourceCardStyle}>
      <div className="min-w-0">
        <div className="font-mono" style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)" }}>
          {source.statement_type} {source.cd_conta ?? source.line_id_base}
        </div>
        <div className="truncate" style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>
          {source.label_snapshot ?? source.line_id_base}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Select
          block={false}
          value={String(source.sign)}
          onChange={(event) => onSignChange(index, Number(event.target.value))}
          style={{ ...controlStyle, width: 92 }}
        >
          <option value="1">Include</option>
          <option value="-1">Subtract</option>
        </Select>
        <Button size="xs" variant="ghost" onClick={() => onRemove(index)}>
          Remove
        </Button>
      </div>
    </div>
  );
}

function ValidationStrip({
  validation,
  entries,
  blockingCount,
  warningCount,
  showDetails,
  touched,
  onToggle,
}: {
  validation: ExcelMappingValidationIssue[];
  entries: ExcelMappingEntry[];
  blockingCount: number;
  warningCount: number;
  showDetails: boolean;
  touched: boolean;
  onToggle: () => void;
}) {
  return (
    <Panel
      dense
      title="Validation"
      subtitle={touched ? "Draft validation. Save before export." : "Saved mapping validation."}
      actions={<Button size="xs" variant="ghost" onClick={onToggle}>{showDetails ? "Hide" : "Show"} details</Button>}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={blockingCount > 0 ? "error" : "ok"}>
          {blockingCount} blocking
        </StatusChip>
        <StatusChip tone={warningCount > 0 ? "warn" : "ok"}>
          {warningCount} warning{warningCount === 1 ? "" : "s"}
        </StatusChip>
        <span style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>
          {validation.length === 0
            ? "Mapping validation passed for the selected company data."
            : friendlyIssueMessage(validation[0], entries)}
        </span>
      </div>
      {showDetails ? (
        <div className="mt-3 max-h-[220px] overflow-auto">
          {validation.slice(0, 60).map((issue) => (
            <div key={`${issue.severity}:${issue.code}:${issue.target_id ?? ""}:${issue.source_id ?? ""}:${issue.message}`} style={validationRowStyle}>
              <span className="font-mono" style={{ color: issue.severity === "error" ? "var(--color-state-err)" : "var(--color-state-warn)", fontSize: "var(--text-2xs)" }}>
                {issue.severity.toUpperCase()} | {issue.code}
              </span>
              <span style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>
                {friendlyIssueMessage(issue, entries)}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}

function MetricBox({ label, value, tone }: { label: string; value: string; tone: "neutral" | "ok" | "warn" }) {
  return (
    <div style={{
      background: "var(--color-surface-1)",
      border: "1px solid var(--color-border-subtle)",
      borderRadius: "var(--radius-sm)",
      padding: "8px 10px",
    }}>
      <div style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)", textTransform: "uppercase" }}>
        {label}
      </div>
      <div className="font-mono" style={{ color: tone === "ok" ? "var(--color-state-ok)" : tone === "warn" ? "var(--color-state-warn)" : "var(--color-text-primary)", fontSize: "var(--text-md)", fontWeight: 650 }}>
        {value}
      </div>
    </div>
  );
}

function StatusChip({ children, tone }: { children: ReactNode; tone: "ok" | "warn" | "error" | "info" | "muted" }) {
  return (
    <span style={{
      border: `1px solid ${chipColor(tone)}`,
      borderRadius: "var(--radius-sm)",
      color: chipColor(tone),
      display: "inline-flex",
      fontSize: "var(--text-2xs)",
      fontWeight: 650,
      lineHeight: "14px",
      padding: "1px 5px",
      textTransform: "uppercase",
    }}>
      {children}
    </span>
  );
}

function MiniBadge({ children, tone }: { children: ReactNode; tone: "ok" | "warn" | "error" | "muted" }) {
  return (
    <span style={{
      background: "var(--color-surface-1)",
      border: `1px solid ${chipColor(tone)}`,
      borderRadius: "var(--radius-sm)",
      color: chipColor(tone),
      fontSize: "var(--text-2xs)",
      fontWeight: 600,
      padding: "0 4px",
      whiteSpace: "nowrap",
    }}>
      {children}
    </span>
  );
}

function buildPreviewRows(
  mapping: ExcelMappingDefinition | null,
  workspace: NonNullable<ExcelMappingWorkspaceResult["workspace"]> | null,
  validation: ExcelMappingValidationIssue[],
): PreviewRow[] {
  if (!mapping || !workspace) return [];
  const fallbackById = new Map(workspace.model_preview_rows.map((row) => [row.target_id, row]));
  const rawByKey = new Map(workspace.raw_lines.map((line) => [`${line.statement_type}:${line.line_id_base}`, line]));
  const issuesByTarget = new Map<string, ExcelMappingValidationIssue[]>();
  for (const issue of validation) {
    if (!issue.target_id) continue;
    issuesByTarget.set(issue.target_id, [...(issuesByTarget.get(issue.target_id) ?? []), issue]);
  }
  const originalEntries = new Map(workspace.mapping.entries.map((entry) => [entry.target_id, entry]));
  return mapping.entries.map((entry) => {
    const fallback = fallbackById.get(entry.target_id);
    const rowIssues = issuesByTarget.get(entry.target_id) ?? [];
    const values_by_period: Record<string, number | null> = {};
    for (const period of workspace.preview_periods) {
      values_by_period[period] = previewValueForEntry(entry, period, rawByKey)
        ?? fallback?.values_by_period[period]
        ?? null;
    }
    return {
      target_id: entry.target_id,
      target_label: entry.target_label,
      group: entry.group,
      statement_type: entry.statement_type,
      display_order: entry.display_order,
      indent_level: entry.indent_level,
      required: entry.required,
      operation: entry.operation,
      is_subtotal: entry.is_subtotal,
      source_count: entry.sources.length,
      warning_count: rowIssues.filter((issue) => issue.severity !== "error").length,
      error_count: rowIssues.filter((issue) => issue.severity === "error").length,
      values_by_period,
      rowIssues,
      edited: !sameEntryMapping(entry, originalEntries.get(entry.target_id)),
    };
  });
}

function previewValueForEntry(
  entry: ExcelMappingEntry,
  period: string,
  rawByKey: Map<string, ExcelMappingRawLine>,
): number | null {
  if (!OPERATIONS.some((operation) => operation.value === entry.operation)) return null;
  const sources = entry.operation === "direct" ? entry.sources.slice(0, 1) : entry.sources;
  if (sources.length === 0) return null;
  let total = 0;
  for (const source of sources) {
    const line = rawByKey.get(`${source.statement_type}:${source.line_id_base}`);
    const value = line?.sample_values_by_period?.[period];
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    const sign = entry.operation === "sum_with_sign" && source.sign < 0 ? -1 : 1;
    total += sign * value;
  }
  return total;
}

function sameEntryMapping(entry: ExcelMappingEntry, original: ExcelMappingEntry | undefined): boolean {
  if (!original) return false;
  if (entry.operation !== original.operation || entry.sources.length !== original.sources.length) return false;
  return entry.sources.every((source, index) => {
    const other = original.sources[index];
    return other
      && source.statement_type === other.statement_type
      && source.line_id_base === other.line_id_base
      && source.sign === other.sign;
  });
}

function buildStatementGroups(rows: PreviewRow[]): StatementGroupSummary[] {
  const rowsByStatement = new Map<string, PreviewRow[]>();
  for (const row of rows) {
    const statementType = canonicalStatementType(row.statement_type);
    rowsByStatement.set(statementType, [...(rowsByStatement.get(statementType) ?? []), row]);
  }

  const statementTypes = new Set<string>(CORE_STATEMENT_TYPES);
  for (const statementType of rowsByStatement.keys()) {
    statementTypes.add(statementType);
  }

  return [...statementTypes]
    .sort(compareStatementTypes)
    .map((statementType) => {
      const statementRows = [...(rowsByStatement.get(statementType) ?? [])]
        .sort((a, b) => a.display_order - b.display_order);
      const warningCount = statementRows.reduce((total, row) => total + row.warning_count, 0);
      const errorCount = statementRows.reduce((total, row) => total + row.error_count, 0);
      return {
        statementType,
        label: statementLabel(statementType),
        description: statementDescription(statementType),
        rows: statementRows,
        rowCount: statementRows.length,
        mappedCount: statementRows.filter((row) => row.source_count > 0).length,
        sourceCount: statementRows.reduce((total, row) => total + row.source_count, 0),
        warningCount,
        errorCount,
        editedCount: statementRows.filter((row) => row.edited).length,
        rowIds: statementRows.map((row) => row.target_id).join("|"),
      };
    });
}

function buildSourceStatementOptions(rawLines: ExcelMappingRawLine[], entry: ExcelMappingEntry | null) {
  const statementTypes = new Set<string>(CORE_STATEMENT_TYPES);
  if (entry?.statement_type) {
    statementTypes.add(canonicalStatementType(entry.statement_type));
  }
  for (const line of rawLines) {
    statementTypes.add(canonicalStatementType(line.statement_type));
  }
  return [...statementTypes]
    .sort(compareStatementTypes)
    .map((statementType) => ({
      value: statementType,
      label: statementLabel(statementType),
    }));
}

function canonicalStatementType(value: string | null | undefined): string {
  const statementType = String(value ?? "").trim().toUpperCase();
  return statementType || UNKNOWN_STATEMENT_TYPE;
}

function compareStatementTypes(a: string, b: string): number {
  const aIndex = STATEMENT_ORDER.findIndex((statementType) => statementType === a);
  const bIndex = STATEMENT_ORDER.findIndex((statementType) => statementType === b);
  if (aIndex !== -1 || bIndex !== -1) {
    return (aIndex === -1 ? 1000 : aIndex) - (bIndex === -1 ? 1000 : bIndex);
  }
  if (a === UNKNOWN_STATEMENT_TYPE) return 1;
  if (b === UNKNOWN_STATEMENT_TYPE) return -1;
  return a.localeCompare(b);
}

function statementLabel(statementType: string): string {
  if (statementType === UNKNOWN_STATEMENT_TYPE) return "Unknown Statement";
  return STATEMENT_LABELS[statementType] ?? statementType;
}

function statementDescription(statementType: string): string {
  if (statementType === UNKNOWN_STATEMENT_TYPE) {
    return "Statement family not recognized by the current UI";
  }
  return STATEMENT_DESCRIPTIONS[statementType] ?? "Additional statement family from local data";
}

function statementSummaryText(statement: StatementGroupSummary): string {
  const issueText = statement.errorCount > 0
    ? `${statement.errorCount} error${statement.errorCount === 1 ? "" : "s"}`
    : statement.warningCount > 0
      ? `${statement.warningCount} warning${statement.warningCount === 1 ? "" : "s"}`
      : "clean";
  return `${statement.rowCount} row${statement.rowCount === 1 ? "" : "s"}, ${statement.mappedCount} mapped, ${statement.sourceCount} source${statement.sourceCount === 1 ? "" : "s"}, ${issueText}`;
}

function groupRows(rows: PreviewRow[]) {
  const groups: Array<{ name: string; rows: PreviewRow[] }> = [];
  for (const row of rows) {
    let group = groups.find((item) => item.name === row.group);
    if (!group) {
      group = { name: row.group, rows: [] };
      groups.push(group);
    }
    group.rows.push(row);
  }
  return groups;
}

function validateDraft(
  mapping: ExcelMappingDefinition,
  rawLines: ExcelMappingRawLine[],
): ExcelMappingValidationIssue[] {
  const rawKeys = new Set(rawLines.map((line) => `${line.statement_type}:${line.line_id_base}`));
  const issues: ExcelMappingValidationIssue[] = [];
  const usage = new Map<string, string[]>();
  for (const entry of mapping.entries) {
    if (!OPERATIONS.some((operation) => operation.value === entry.operation)) {
      issues.push({
        severity: "error",
        code: "invalid_operation",
        message: `Invalid operation for ${entry.target_label}.`,
        target_id: entry.target_id,
        source_id: null,
      });
    }
    if (entry.required && entry.sources.length === 0) {
      issues.push({
        severity: "warning",
        code: "required_mapping_empty",
        message: `${entry.target_label} has no mapped CVM source line.`,
        target_id: entry.target_id,
        source_id: null,
      });
    }
    for (const source of entry.sources) {
      const sourceId = `${source.statement_type}:${source.line_id_base}`;
      usage.set(sourceId, [...(usage.get(sourceId) ?? []), entry.target_id]);
      if (source.statement_type !== entry.statement_type) {
        issues.push({
          severity: "error",
          code: "statement_type_mismatch",
          message: `${sourceId} cannot feed a ${entry.statement_type} row.`,
          target_id: entry.target_id,
          source_id: sourceId,
        });
      }
      if (!rawKeys.has(sourceId)) {
        issues.push({
          severity: "warning",
          code: "source_missing_for_company",
          message: `${sourceId} is not present for this company.`,
          target_id: entry.target_id,
          source_id: sourceId,
        });
      }
    }
  }
  for (const [sourceId, targets] of usage) {
    if (new Set(targets).size > 1) {
      issues.push({
        severity: "warning",
        code: "source_mapped_multiple_times",
        message: `${sourceId} is used in multiple Model rows.`,
        target_id: null,
        source_id: sourceId,
      });
    }
  }
  return issues;
}

function mergeValidationIssues(
  serverIssues: ExcelMappingValidationIssue[],
  draftIssues: ExcelMappingValidationIssue[],
): ExcelMappingValidationIssue[] {
  const merged: ExcelMappingValidationIssue[] = [];
  const seen = new Set<string>();
  for (const issue of [...serverIssues, ...draftIssues]) {
    const key = [
      issue.severity,
      issue.code,
      issue.target_id ?? "",
      issue.source_id ?? "",
      issue.message,
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(issue);
  }
  return merged;
}

function friendlyFormula(entry: ExcelMappingEntry): string {
  if (entry.sources.length === 0) {
    return `${entry.target_label} has no mapped CVM source line yet.`;
  }
  const names = entry.sources.map((source) => `${source.cd_conta ?? source.line_id_base} (${source.label_snapshot ?? source.line_id_base})`);
  if (entry.operation === "direct") {
    return `${entry.target_label} uses ${names[0]}, scaled from R$ thousands to R$ millions.`;
  }
  if (entry.operation === "sum_with_sign") {
    return `${entry.target_label} combines ${entry.sources.length} CVM lines, subtracting lines marked as Subtract, then scales to R$ millions.`;
  }
  return `${entry.target_label} sums ${entry.sources.length} CVM lines, then scales from R$ thousands to R$ millions.`;
}

function friendlyIssueMessage(issue: ExcelMappingValidationIssue, entries: ExcelMappingEntry[] = []): string {
  if (issue.target_id) {
    const label = entries.find((entry) => entry.target_id === issue.target_id)?.target_label;
    if (issue.code === "required_mapping_empty" && label) {
      return `${label} has no mapped CVM source line.`;
    }
    if (issue.code === "source_missing_for_company" && label) {
      return `${label} references a CVM line that does not exist for the selected company.`;
    }
  }
  if (issue.code === "source_mapped_multiple_times") {
    return "This CVM line is used by multiple Model rows.";
  }
  if (issue.code === "raw_lines_unmapped") {
    return issue.message;
  }
  return issue.message;
}

function latestPreviewValue(row: PreviewRow | null, periods: string[]) {
  if (!row) return null;
  const latest = periods.at(-1);
  return latest ? row.values_by_period[latest] : null;
}

function formatModelValue(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  const absolute = Math.abs(value);
  const formatted = absolute.toLocaleString("en-US", {
    maximumFractionDigits: absolute >= 100 ? 0 : 1,
  });
  return value < 0 ? `(${formatted})` : formatted;
}

function chipColor(tone: "ok" | "warn" | "error" | "info" | "muted") {
  if (tone === "ok") return "var(--color-state-ok)";
  if (tone === "warn") return "var(--color-state-warn)";
  if (tone === "error") return "var(--color-state-err)";
  if (tone === "info") return "var(--color-id-ticker)";
  return "var(--color-text-tertiary)";
}

function exportStatusColor(status: string) {
  if (status === "success") return "var(--color-state-ok)";
  if (status === "error") return "var(--color-state-err)";
  if (status === "running") return "var(--color-state-warn)";
  return "var(--color-text-tertiary)";
}

function exportStatusMessage(status: string, error: string | null, fileName: string | null) {
  if (status === "running") return "Export is running with the active saved mapping.";
  if (status === "success") return fileName ? `Export completed: ${fileName}` : "Export completed.";
  if (status === "error") return error ?? "Export failed.";
  if (status === "unavailable") return "Export is available in the desktop app.";
  return "Export will use the active saved preset and the selected period scope.";
}

function issueLineStyle(issue: ExcelMappingValidationIssue): CSSProperties {
  return {
    background: "var(--color-surface-1)",
    border: `1px solid ${issue.severity === "error" ? "var(--color-state-err)" : "var(--color-state-warn)"}`,
    borderRadius: "var(--radius-sm)",
    color: issue.severity === "error" ? "var(--color-state-err)" : "var(--color-state-warn)",
    fontSize: "var(--text-xs)",
    padding: "6px 8px",
  };
}

const labelStyle: CSSProperties = {
  color: "var(--color-text-secondary)",
  display: "block",
  fontSize: "var(--text-xs)",
};
const inputStyle: CSSProperties = {
  width: "100%",
  background: "var(--color-surface-2)",
  border: "1px solid var(--color-border-default)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text-primary)",
  fontSize: "var(--text-sm)",
  marginTop: 4,
  outline: "none",
  padding: "6px 10px",
};
const controlStyle: CSSProperties = {
  fontSize: "var(--text-sm)",
  marginTop: 4,
  padding: "5px 8px",
};
const tableFrameStyle: CSSProperties = {
  background: "var(--color-surface-2)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
};
const tableHeaderRowStyle: CSSProperties = {
  background: "var(--color-surface-1)",
  borderBottom: "1px solid var(--color-border-default)",
  color: "var(--color-text-tertiary)",
  textTransform: "uppercase",
};
const tableHeaderCellStyle: CSSProperties = {
  fontSize: "var(--text-2xs)",
  fontWeight: 650,
  padding: "7px 9px",
  textAlign: "right",
  whiteSpace: "nowrap",
};
const sectionRowStyle: CSSProperties = {
  color: "var(--color-action-primary)",
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  letterSpacing: 0,
  padding: "7px 9px",
  textAlign: "left",
  textTransform: "uppercase",
};
const modelRowHeaderStyle: CSSProperties = {
  color: "var(--color-text-primary)",
  minWidth: 320,
  padding: "7px 9px",
  textAlign: "left",
  verticalAlign: "middle",
};
const sourceCellStyle: CSSProperties = {
  color: "var(--color-text-secondary)",
  padding: "7px 9px",
  textAlign: "left",
  verticalAlign: "middle",
};
const valueCellStyle: CSSProperties = {
  color: "var(--color-text-primary)",
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-xs)",
  fontVariantNumeric: "tabular-nums",
  padding: "7px 9px",
  textAlign: "right",
  whiteSpace: "nowrap",
};
const sourceCardStyle: CSSProperties = {
  alignItems: "center",
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
  display: "flex",
  gap: 8,
  justifyContent: "space-between",
  padding: "8px 9px",
};
const formulaBoxStyle: CSSProperties = {
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-default)",
  borderRadius: "var(--radius-sm)",
  padding: "8px 9px",
};
const emptyInsetStyle: CSSProperties = {
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
  color: "var(--color-text-tertiary)",
  fontSize: "var(--text-xs)",
  padding: "12px",
};
const validationRowStyle: CSSProperties = {
  borderBottom: "1px solid var(--color-border-subtle)",
  display: "grid",
  gap: 4,
  padding: "7px 0",
};
const overlayStyle: CSSProperties = {
  inset: 0,
  position: "fixed",
  zIndex: "var(--z-overlay)",
};
const overlayBackdropStyle: CSSProperties = {
  background: "rgba(0, 0, 0, 0.58)",
  border: 0,
  cursor: "default",
  inset: 0,
  padding: 0,
  position: "absolute",
};
const drawerStyle: CSSProperties = {
  background: "var(--color-surface-2)",
  borderLeft: "1px solid var(--color-border-strong)",
  bottom: 0,
  boxShadow: "var(--shadow-drawer)",
  maxWidth: "min(720px, 100vw)",
  position: "absolute",
  right: 0,
  top: 0,
  width: 620,
};
const drawerHeaderStyle: CSSProperties = {
  alignItems: "flex-start",
  borderBottom: "1px solid var(--color-border-subtle)",
  display: "flex",
  gap: 12,
  justifyContent: "space-between",
  padding: 12,
};
const rawLineStyle: CSSProperties = {
  alignItems: "center",
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
  display: "flex",
  gap: 10,
  justifyContent: "space-between",
  padding: "9px 10px",
};
