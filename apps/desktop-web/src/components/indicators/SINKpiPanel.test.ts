import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { SINKPIObservation, SINKPISourceStatus } from "@/lib/bridge/types";
import { createMockBridge } from "@/lib/bridge/mock";
import { MOCK_KPI_CATALOG, MOCK_SIN_DASHBOARD, MOCK_SIN_VALUES } from "@/lib/bridge/mockEnergyFixtures";

import {
  buildGenerationMixRow,
  describeSINSourceHealth,
  GenerationMix,
  PowerSystemViewToggle,
  SIN_ANALYTICAL_FAMILIES,
  SIN_KPI_META_FALLBACK,
  normalizeSINCatalogUnit,
  SourcePanel,
  trendPresentationState,
} from "./SINKpiPanel";
import { CHANGE_COMPARISON_LABEL } from "./explorer/IndicatorDetailPanel";

const latestIndex = new Map<string, SINKPIObservation>();

function sourceStatus(overrides: Partial<SINKPISourceStatus>): SINKPISourceStatus {
  return {
    source: "ONS",
    dataset: "cmo_semihorario",
    frequency: "semi-hourly",
    last_snapshot_at: "2026-07-12T10:00:00",
    local_records_count: 12,
    last_status: "success",
    last_error: null,
    latest_reference_datetime: "2026-07-12T09:30:00",
    latest_successful_snapshot_at: "2026-07-12T10:00:00",
    latest_attempt_at: "2026-07-12T10:00:00",
    latest_attempt_status: "success",
    latest_failure_at: null,
    health_state: "success",
    is_missing: false,
    is_stale: false,
    ...overrides,
  };
}

describe("SIN Power System presentation", () => {
  it("keeps price audit-table fallback units explicit", () => {
    expect(SIN_KPI_META_FALLBACK["energy_utilities.sin.cmo_brl_mwh"]?.unit).toBe("R$/MWh");
    expect(SIN_KPI_META_FALLBACK["energy_utilities.sin.pld_brl_mwh"]?.unit).toBe("R$/MWh");
  });

  it("preserves the catalog PLD unit for the audit table", () => {
    expect(normalizeSINCatalogUnit("R$/MWh")).toBe("R$/MWh");
  });

  it("defines only the four approved analytical families and keeps price confirmatory", () => {
    expect(SIN_ANALYTICAL_FAMILIES).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "Load and demand pressure", role: "Explanatory driver" }),
      expect.objectContaining({ title: "Generation supply and mix", role: "Explanatory driver" }),
      expect.objectContaining({ title: "Hydro buffer and inflow", role: "Explanatory driver" }),
      expect.objectContaining({ title: "System price confirmation", role: "Confirmatory / outcome signal" }),
    ]));
    expect(SIN_ANALYTICAL_FAMILIES.map((family) => family.title)).not.toContain("Capacity and firm-supply headroom");
  });

  it("keeps usable ONS evidence successful while PLD is failed and missing", () => {
    expect(describeSINSourceHealth(sourceStatus({ source: "ONS" }))).toMatchObject({
      label: "success",
      currentError: null,
    });
    expect(describeSINSourceHealth(sourceStatus({
      source: "CCEE",
      dataset: "pld_horario",
      local_records_count: 0,
      health_state: "failed",
      is_missing: true,
      last_error: "HTTP 403",
    }))).toMatchObject({
      label: "failed",
      missing: true,
      stale: false,
      currentError: "HTTP 403",
    });
  });

  it("keeps stale evidence visible when a newer source problem makes the state partial", () => {
    expect(describeSINSourceHealth(sourceStatus({
      health_state: "partial",
      is_stale: true,
      last_error: "CCEE request failed",
    }))).toMatchObject({
      label: "partial",
      stale: true,
      currentError: "CCEE request failed",
    });
  });

  it("keeps missing distinct from a source failure", () => {
    expect(describeSINSourceHealth(sourceStatus({
      local_records_count: 0,
      health_state: "missing",
      is_missing: true,
      last_error: null,
    }))).toMatchObject({ label: "missing", missing: true, currentError: null });
  });

  it("does not present a historical failure as current after a newer success", () => {
    expect(describeSINSourceHealth(sourceStatus({
      latest_failure_at: "2026-07-10T10:00:00",
      last_error: null,
      health_state: "success",
    }))).toMatchObject({ currentError: null, label: "success" });
  });

  it("preserves null mix values as unavailable while measured zero remains a value", () => {
    latestIndex.set("energy_utilities.sin.mix_hydro_pct|S", {
      kpi_id: "energy_utilities.sin.mix_hydro_pct",
      subsystem_code: "S",
      reference_datetime: "2026-07-12T00:00:00",
      value: 0,
      unit: "%",
      source: "ONS",
      subsystem_name: "South",
      source_dataset: "test",
      source_field: "test",
      snapshot_id: "test",
      data_quality_status: "ok",
    });
    const row = buildGenerationMixRow(latestIndex, "S");

    expect(row.available).toBe(true);
    expect(row.parts.find((part) => part.label === "Hydro")?.value).toBe(0);
    expect(row.parts.find((part) => part.label === "Thermal")?.value).toBeNull();
    expect(buildGenerationMixRow(new Map(), "N")).toMatchObject({ available: false });
  });

  it("renders measured zero while keeping missing mix components unavailable", () => {
    const markup = renderToStaticMarkup(createElement(GenerationMix, { latestIndex }));

    expect(markup).toContain("Measured zero: Hydro 0%");
    expect(markup).toContain("Partial measurement");
  });

  it("renders current failed and missing source evidence with local provenance", () => {
    const markup = renderToStaticMarkup(createElement(SourcePanel, {
      dashboard: {
        last_successful_update: null,
        latest_reference_datetime: null,
        is_empty: true,
        is_stale: false,
        observations: [],
        source_statuses: [sourceStatus({
          source: "CCEE",
          dataset: "pld_horario",
          local_records_count: 0,
          health_state: "failed",
          is_missing: true,
          last_error: "HTTP 403",
        })],
        refresh_running: false,
        refresh_error: null,
      },
    }));

    expect(markup).toContain("failed");
    expect(markup).toContain("No usable local rows");
    expect(markup).toContain("Latest local");
    expect(markup).toContain("HTTP 403");
  });

  it("renders the overview and trends switch as pressed native buttons", () => {
    const markup = renderToStaticMarkup(createElement(PowerSystemViewToggle, {
      viewMode: "matrix",
      onViewModeChange: () => undefined,
    }));

    expect(markup).toContain('aria-pressed="true"');
    expect(markup).toContain('aria-pressed="false"');
    expect(markup).toContain("Overview");
    expect(markup).toContain("Trends");
  });

  it("keeps trend request errors distinct from empty and selection-required states", () => {
    expect(trendPresentationState({ isLoading: false, isError: true, hasSeries: false, hasSelection: true })).toBe("error");
    expect(trendPresentationState({ isLoading: false, isError: false, hasSeries: false, hasSelection: false })).toBe("selection-required");
    expect(trendPresentationState({ isLoading: true, isError: false, hasSeries: false, hasSelection: false })).toBe("selection-required");
    expect(trendPresentationState({ isLoading: false, isError: false, hasSeries: false, hasSelection: true })).toBe("empty");
    expect(trendPresentationState({ isLoading: true, isError: false, hasSeries: false, hasSelection: true })).toBe("loading");
  });

  it("uses a frequency-neutral adjacent-point change label", () => {
    expect(CHANGE_COMPARISON_LABEL).toBe("vs prior observation");
  });

  it("keeps failed and missing mock PLD out of both local dashboard and trend reads", async () => {
    const pldId = "energy_utilities.sin.pld_brl_mwh";
    const cmoId = "energy_utilities.sin.cmo_brl_mwh";
    const mockBridge = createMockBridge();
    const pldStatus = MOCK_SIN_DASHBOARD.source_statuses.find((status) => status.dataset === "pld_horario");

    expect(pldStatus).toMatchObject({ health_state: "failed", is_missing: true, local_records_count: 0 });
    expect(MOCK_KPI_CATALOG.some((entry) => entry.kpi_id === pldId)).toBe(true);
    expect(MOCK_SIN_DASHBOARD.observations.some((row) => row.kpi_id === pldId)).toBe(false);
    expect(MOCK_SIN_VALUES.some((row) => row.kpi_id === pldId)).toBe(false);

    const pldSeries = await mockBridge.get_sin_kpi_series?.({ kpi_ids: [pldId] });
    const cmoSeries = await mockBridge.get_sin_kpi_series?.({ kpi_ids: [cmoId] });

    expect(pldSeries).toMatchObject({ count: 0, values: [] });
    expect(cmoSeries?.count).toBeGreaterThan(0);
    expect(cmoSeries?.values.every((row) => row.kpi_id === cmoId)).toBe(true);
    expect(trendPresentationState({
      isLoading: false,
      isError: false,
      hasSeries: pldSeries?.count ? pldSeries.count > 0 : false,
      hasSelection: true,
    })).toBe("empty");
  });
});
