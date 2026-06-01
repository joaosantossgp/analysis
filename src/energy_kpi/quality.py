"""Energy KPI data quality checks.

Each check produces a DQCheckResult and inserts a row into data_quality_checks.
Checks: schema, required_fields, iso_validity, unit_consistency, duplicate_pk,
        missing_coverage, impossible_negatives, share_bounds, yoy_outliers,
        conflict_flags, reproducibility.

Severity: 'info' | 'warn' | 'error'
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.energy_kpi.catalog import CATALOG_BY_ID, _ENERGY_CATALOG
from src.energy_kpi.ingest_owid import V1_ISO_CODES

logger = logging.getLogger(__name__)

# OWID fields that must appear in the normalized tidy frame
REQUIRED_OWID_FIELDS: frozenset[str] = frozenset(
    k.primary_source_field
    for k in _ENERGY_CATALOG
    if k.v1_status == "v1_required" and k.primary_source == "OWID" and k.primary_source_field
    and k.calculation_method == "direct"
)

# KPIs where value must be ≥ 0 (negative impossible)
NON_NEGATIVE_KPIS: frozenset[str] = frozenset(
    k.kpi_id for k in _ENERGY_CATALOG
    if k.kpi_type in ("mix_share", "volume", "per_capita", "intensity", "emissions", "capacity")
    and k.kpi_id != "energy_utilities.country.elec_net_imports"
)

# KPIs where value is a share [0, 100]
SHARE_KPIS: frozenset[str] = frozenset(
    k.kpi_id for k in _ENERGY_CATALOG if k.kpi_type == "mix_share"
)

# YoY outlier threshold for share KPIs (percentage-point jump per year)
YOY_SHARE_WARN_THRESHOLD = 30.0


@dataclass(frozen=True)
class DQCheckResult:
    check_id: str
    check_name: str
    severity: str
    passed: bool
    details: dict[str, Any]
    run_id: str


def _insert_check(conn, result: DQCheckResult) -> None:
    conn.execute(text("""
        INSERT INTO data_quality_checks
            (check_id, run_id, check_name, severity, passed, details_json, created_at)
        VALUES
            (:cid, :rid, :name, :sev, :passed, :details, :ts)
    """), {
        "cid": result.check_id,
        "rid": result.run_id,
        "name": result.check_name,
        "sev": result.severity,
        "passed": int(result.passed),
        "details": json.dumps(result.details),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })


def _make_result(
    run_id: str,
    check_name: str,
    severity: str,
    passed: bool,
    details: dict[str, Any],
) -> DQCheckResult:
    return DQCheckResult(
        check_id=str(uuid.uuid4()),
        check_name=check_name,
        severity=severity,
        passed=passed,
        details=details,
        run_id=run_id,
    )


def run_quality_checks(
    conn,
    run_id: str,
    tidy_df: pd.DataFrame,
) -> list[DQCheckResult]:
    """Run all DQ checks against the tidy merged DataFrame.

    Inserts each result into data_quality_checks and returns the list.
    Never raises — errors in individual checks are logged and reported as failed.
    """
    results: list[DQCheckResult] = []

    def _check(fn):
        try:
            r = fn()
            if r is not None:
                results.append(r)
                _insert_check(conn, r)
        except Exception as exc:
            logger.warning("DQ check %s failed with exception: %s", fn.__name__, exc)
            r = _make_result(run_id, fn.__name__, "error", False, {"exception": str(exc)})
            results.append(r)
            _insert_check(conn, r)

    # 1. Schema — required OWID source fields present in tidy frame
    def check_schema():
        present = set(tidy_df["source_field"].unique()) if "source_field" in tidy_df.columns else set()
        missing = REQUIRED_OWID_FIELDS - present
        return _make_result(
            run_id, "schema_required_fields", "error" if missing else "info",
            not bool(missing),
            {"missing_owid_fields": sorted(missing), "present_count": len(present)},
        )
    _check(check_schema)

    # 2. Required columns — iso_code, period, value not null
    def check_required_fields():
        # 'value' is intentionally excluded — null values are data coverage gaps
        # caught by check_missing_coverage, not schema errors.
        issues = {}
        for col in ("kpi_id", "iso_code", "period"):
            if col not in tidy_df.columns:
                issues[col] = "column_missing"
            else:
                null_count = int(tidy_df[col].isna().sum())
                if null_count:
                    issues[col] = null_count
        return _make_result(
            run_id, "required_fields_not_null", "error" if issues else "info",
            not bool(issues), {"issues": issues, "total_rows": len(tidy_df)},
        )
    _check(check_required_fields)

    # 3. ISO validity — all iso_codes in country_dimension
    def check_iso_validity():
        if "iso_code" not in tidy_df.columns:
            return _make_result(run_id, "iso_validity", "warn", False, {"error": "no iso_code column"})
        valid_iso = V1_ISO_CODES
        invalid = set(tidy_df["iso_code"].dropna().unique()) - valid_iso
        return _make_result(
            run_id, "iso_validity", "warn" if invalid else "info",
            not bool(invalid),
            {"unexpected_iso_codes": sorted(invalid)},
        )
    _check(check_iso_validity)

    # 4. Unit consistency — each kpi_id has consistent unit vs catalog
    def check_unit_consistency():
        if "unit" not in tidy_df.columns or "kpi_id" not in tidy_df.columns:
            return None
        mismatches = {}
        for kpi_id, grp in tidy_df.groupby("kpi_id"):
            catalog_entry = CATALOG_BY_ID.get(str(kpi_id))
            if catalog_entry is None:
                continue
            data_units = set(grp["unit"].dropna().unique())
            if data_units and catalog_entry.unit not in data_units:
                mismatches[str(kpi_id)] = {
                    "expected": catalog_entry.unit,
                    "found": sorted(data_units),
                }
        return _make_result(
            run_id, "unit_consistency", "warn" if mismatches else "info",
            not bool(mismatches), {"mismatches": mismatches},
        )
    _check(check_unit_consistency)

    # 5. Duplicate PK — (kpi_id, iso_code, period) should be unique
    def check_duplicate_pk():
        if not all(c in tidy_df.columns for c in ("kpi_id", "iso_code", "period")):
            return None
        dupes = tidy_df.duplicated(subset=["kpi_id", "iso_code", "period"], keep=False)
        dupe_count = int(dupes.sum())
        if dupe_count:
            examples = tidy_df[dupes][["kpi_id", "iso_code", "period"]].head(5).to_dict(orient="records")
        else:
            examples = []
        return _make_result(
            run_id, "duplicate_pk", "error" if dupe_count else "info",
            dupe_count == 0,
            {"duplicate_rows": dupe_count, "examples": examples},
        )
    _check(check_duplicate_pk)

    # 6. Missing coverage — report % missing per KPI per country
    def check_missing_coverage():
        if "value" not in tidy_df.columns:
            return None
        summary = {}
        for kpi_id in tidy_df["kpi_id"].unique():
            grp = tidy_df[tidy_df["kpi_id"] == kpi_id]
            null_pct = round(grp["value"].isna().mean() * 100, 1)
            if null_pct > 0:
                summary[str(kpi_id)] = null_pct
        return _make_result(
            run_id, "missing_coverage", "info",
            True,  # coverage gaps are informational, not errors
            {"kpis_with_nulls": summary},
        )
    _check(check_missing_coverage)

    # 7. Impossible negatives — shares, volumes, per_capita, intensity must be ≥ 0
    def check_impossible_negatives():
        if "value" not in tidy_df.columns:
            return None
        neg_mask = tidy_df["kpi_id"].isin(NON_NEGATIVE_KPIS) & (tidy_df["value"] < 0)
        neg_count = int(neg_mask.sum())
        examples = []
        if neg_count:
            examples = tidy_df[neg_mask][["kpi_id", "iso_code", "period", "value"]].head(5).to_dict(orient="records")
        return _make_result(
            run_id, "impossible_negatives", "error" if neg_count else "info",
            neg_count == 0,
            {"negative_value_rows": neg_count, "examples": examples},
        )
    _check(check_impossible_negatives)

    # 8. Share bounds [0, 100]
    def check_share_bounds():
        if "value" not in tidy_df.columns:
            return None
        share_rows = tidy_df[tidy_df["kpi_id"].isin(SHARE_KPIS)]
        out_of_bounds = share_rows[
            (share_rows["value"] < 0) | (share_rows["value"] > 100)
        ]
        count = len(out_of_bounds)
        examples = out_of_bounds[["kpi_id", "iso_code", "period", "value"]].head(5).to_dict(orient="records") if count else []
        return _make_result(
            run_id, "share_bounds", "error" if count else "info",
            count == 0,
            {"out_of_bounds_rows": count, "examples": examples},
        )
    _check(check_share_bounds)

    # 9. YoY outliers — warn if share jumps > 30pp in a single year
    def check_yoy_outliers():
        if "value" not in tidy_df.columns:
            return None
        outliers = []
        share_df = tidy_df[tidy_df["kpi_id"].isin(SHARE_KPIS)].copy()
        if share_df.empty:
            return None
        share_df_sorted = share_df.sort_values(["kpi_id", "iso_code", "period"])
        share_df_sorted["prev"] = share_df_sorted.groupby(["kpi_id", "iso_code"])["value"].shift(1)
        share_df_sorted["yoy_jump"] = (share_df_sorted["value"] - share_df_sorted["prev"]).abs()
        jumps = share_df_sorted[share_df_sorted["yoy_jump"] > YOY_SHARE_WARN_THRESHOLD]
        for _, row in jumps.head(10).iterrows():
            outliers.append({
                "kpi_id": row["kpi_id"],
                "iso_code": row["iso_code"],
                "period": int(row["period"]),
                "yoy_jump_pp": round(float(row["yoy_jump"]), 1),
            })
        return _make_result(
            run_id, "yoy_outliers", "warn" if outliers else "info",
            not bool(outliers),
            {"outlier_count": len(outliers), "examples": outliers},
        )
    _check(check_yoy_outliers)

    # 10. Conflict flags — summarize top conflicts
    def check_conflict_flags():
        if "source_conflict" not in tidy_df.columns:
            return _make_result(run_id, "conflict_flags", "info", True, {"conflicts": 0})
        conflict_rows = tidy_df[tidy_df["source_conflict"].astype(bool)]
        count = len(conflict_rows)
        examples = []
        if count:
            examples = conflict_rows[["kpi_id", "iso_code", "period",
                                      "value_owid", "value_ember"]].head(10).to_dict(orient="records")
        return _make_result(
            run_id, "conflict_flags", "warn" if count else "info",
            True,  # conflicts are informational in v1 (OWID-only so no conflicts possible yet)
            {"conflict_rows": count, "top_conflicts": examples},
        )
    _check(check_conflict_flags)

    # 11. Reproducibility — every row has a non-null snapshot_id
    def check_reproducibility():
        if "snapshot_id" not in tidy_df.columns:
            return _make_result(run_id, "reproducibility", "error", False,
                                {"error": "no snapshot_id column"})
        missing = int(tidy_df["snapshot_id"].isna().sum())
        return _make_result(
            run_id, "reproducibility", "error" if missing else "info",
            missing == 0,
            {"rows_without_snapshot_id": missing, "total_rows": len(tidy_df)},
        )
    _check(check_reproducibility)

    passed_count = sum(1 for r in results if r.passed)
    logger.info(
        "DQ run %s: %d checks, %d passed, %d failed",
        run_id[:8], len(results), passed_count, len(results) - passed_count,
    )
    return results
