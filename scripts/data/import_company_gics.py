# -*- coding: utf-8 -*-
"""Import approved company-level GICS classifications into companies.

Default mode is dry-run. The script never infers GICS from CVM/B3/native
sector labels and only updates rows matched by cd_cvm from the approved CSV.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.platform.db import build_engine  # noqa: E402
from src.companies.gics_manual_mapping import GICS_11_SECTORS  # noqa: E402
from src.companies.sector_taxonomy import sector_slugify  # noqa: E402
from src.platform.settings import build_settings  # noqa: E402

DEFAULT_MAPPING_PATH = ROOT / "data" / "import" / "gics_mapping.csv"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "gics_backfill_report.json"
REQUIRED_COLUMNS = ("cd_cvm", "gics_sector", "gics_sub_industry", "source", "as_of_date")
OPTIONAL_DIAGNOSTIC_COLUMNS = ("ticker", "company_name", "cnpj", "notes")
REQUIRED_COMPANY_COLUMNS = ("cd_cvm", "gics_sector", "gics_sub_industry")


@dataclass(frozen=True)
class MappingRow:
    row_number: int
    cd_cvm: int
    gics_sector: str
    gics_sub_industry: str
    source: str
    as_of_date: str
    ticker: str | None = None
    company_name: str | None = None
    cnpj: str | None = None
    notes: str | None = None

    def to_report(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "cd_cvm": self.cd_cvm,
            "gics_sector": self.gics_sector,
            "gics_sub_industry": self.gics_sub_industry,
            "source": self.source,
            "as_of_date": self.as_of_date,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "cnpj": self.cnpj,
            "notes": self.notes,
        }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _normalize_ticker(value: Any) -> str | None:
    ticker = _clean(value)
    if ticker is None:
        return None
    ticker = ticker.upper()
    if ticker.endswith(".SA"):
        ticker = ticker[:-3]
    return ticker or None


def _normalize_cnpj(value: Any) -> str | None:
    cnpj = _clean(value)
    if cnpj is None:
        return None
    digits = re.sub(r"\D+", "", cnpj)
    return digits or None


def _normalize_name(value: Any) -> str | None:
    name = _clean(value)
    if name is None:
        return None
    without_accents = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(ch for ch in without_accents if not unicodedata.combining(ch))
    normalized = re.sub(r"\s+", " ", ascii_text).strip().upper()
    return normalized or None


def _canonical_gics_sector(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    for sector in GICS_11_SECTORS:
        if sector.casefold() == normalized:
            return sector
    return None


def _base_report(mode: str, mapping_path: Path, report_path: Path) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": mode,
        "mapping_file": str(mapping_path),
        "report_file": str(report_path),
        "status": "started",
        "errors": [],
        "warnings": [],
        "schema": {},
        "company_universe": {},
        "mappings_read": 0,
        "invalid_rows": [],
        "duplicate_cd_cvm_rows": [],
        "matched_companies": {"count": 0, "items": []},
        "unmatched_mappings": {"count": 0, "items": []},
        "fallback_key_diagnostics": [],
        "companies_would_update": {"count": 0, "items": []},
        "companies_updated": {"count": 0, "items": []},
        "companies_skipped": {"count": 0, "items": []},
        "companies_still_unclassified": {"count": 0, "sample": []},
        "distinct_gics_sectors_after_import": [],
        "distinct_gics_sub_sectors_after_import": [],
        "current_db_gics_field_counts": {},
        "source_values_found": [],
        "as_of_date_values_found": [],
        "report_basis": "actual" if mode in {"apply", "check"} else "projected",
    }


def _write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_company_rows(engine, report: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], set[str]]:
    inspector = inspect(engine)
    if "companies" not in inspector.get_table_names():
        report["errors"].append("Tabela companies nao existe. Execute/regularize o cadastro antes do import GICS.")
        return {}, set()

    columns = {str(column["name"]) for column in inspector.get_columns("companies")}
    missing = [column for column in REQUIRED_COMPANY_COLUMNS if column not in columns]
    report["schema"] = {
        "companies_columns": sorted(columns),
        "required_columns": list(REQUIRED_COMPANY_COLUMNS),
        "missing_required_columns": missing,
        "will_update_gics_sector_slug": "gics_sector_slug" in columns,
    }
    if missing:
        report["errors"].append(
            "Tabela companies sem colunas GICS obrigatorias. Nenhuma alteracao de schema foi feita."
        )
        return {}, columns

    select_columns = [
        "cd_cvm",
        "company_name",
        "cnpj",
        "ticker_b3",
        "gics_sector",
        "gics_sub_industry",
    ]
    if "gics_sector_slug" in columns:
        select_columns.append("gics_sector_slug")
    sql = text(f"SELECT {', '.join(select_columns)} FROM companies ORDER BY cd_cvm")
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(sql).mappings().all()]

    company_rows = {int(row["cd_cvm"]): row for row in rows}
    active_universe_count = _load_active_universe_cache_count()
    report["company_universe"] = {
        "companies_table_count": len(company_rows),
        "active_universe_cache_count": active_universe_count,
        "active_universe_cache_exceeds_companies": (
            active_universe_count is not None and active_universe_count > len(company_rows)
        ),
    }
    if active_universe_count is not None and active_universe_count > len(company_rows):
        report["warnings"].append(
            "O cache de universo ativo tem mais empresas que companies. Rode/valide o seed do catalogo antes do apply."
        )
    return company_rows, columns


def _load_active_universe_cache_count() -> int | None:
    cache_path = ROOT / "data" / "cache" / "active_universe_cache.json"
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        rows = payload.get("rows")
        if isinstance(rows, list):
            return len(rows)
    except Exception:
        return None
    return None


def _read_mapping_file(mapping_path: Path, report: dict[str, Any]) -> list[MappingRow]:
    if not mapping_path.exists():
        report["status"] = "missing_mapping_file"
        report["errors"].append(
            f"Arquivo de mapeamento GICS nao encontrado: {mapping_path}. "
            "Crie data/import/gics_mapping.csv com as colunas obrigatorias."
        )
        return []

    with mapping_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        column_map = {name.strip().lower(): name for name in fieldnames if name is not None}
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in column_map]
        if missing_columns:
            report["status"] = "invalid_mapping_file"
            report["errors"].append(
                f"Arquivo sem colunas obrigatorias: {', '.join(missing_columns)}."
            )
            report["mapping_columns_found"] = fieldnames
            return []

        parsed_rows: list[MappingRow] = []
        raw_valid_rows: list[MappingRow] = []
        duplicate_tracker: dict[int, list[int]] = {}
        for index, raw_row in enumerate(reader, start=2):
            report["mappings_read"] += 1
            errors: list[str] = []

            def cell(name: str) -> str | None:
                return _clean(raw_row.get(column_map[name]))

            cd_raw = cell("cd_cvm")
            cd_cvm: int | None = None
            if cd_raw is None:
                errors.append("cd_cvm vazio")
            else:
                try:
                    cd_cvm = int(cd_raw)
                    if cd_cvm <= 0:
                        errors.append("cd_cvm deve ser positivo")
                except ValueError:
                    errors.append("cd_cvm deve ser inteiro")

            sector_raw = cell("gics_sector")
            sector = _canonical_gics_sector(sector_raw)
            if sector_raw is None:
                errors.append("gics_sector vazio")
            elif sector is None:
                errors.append("gics_sector nao e um dos 11 setores GICS oficiais")

            sub_industry = cell("gics_sub_industry")
            if sub_industry is None:
                errors.append("gics_sub_industry vazio")

            source = cell("source")
            if source is None:
                errors.append("source vazio")

            as_of_date = cell("as_of_date")
            if as_of_date is None:
                errors.append("as_of_date vazio")
            else:
                try:
                    datetime.strptime(as_of_date, "%Y-%m-%d")
                except ValueError:
                    errors.append("as_of_date deve usar formato YYYY-MM-DD")

            if errors or cd_cvm is None or sector is None or sub_industry is None or source is None or as_of_date is None:
                report["invalid_rows"].append(
                    {
                        "row_number": index,
                        "cd_cvm": cd_raw,
                        "errors": errors,
                    }
                )
                continue

            mapping = MappingRow(
                row_number=index,
                cd_cvm=cd_cvm,
                gics_sector=sector,
                gics_sub_industry=sub_industry,
                source=source,
                as_of_date=as_of_date,
                ticker=cell("ticker") if "ticker" in column_map else None,
                company_name=cell("company_name") if "company_name" in column_map else None,
                cnpj=cell("cnpj") if "cnpj" in column_map else None,
                notes=cell("notes") if "notes" in column_map else None,
            )
            raw_valid_rows.append(mapping)
            duplicate_tracker.setdefault(cd_cvm, []).append(index)

        duplicate_codes = {
            cd_cvm: row_numbers
            for cd_cvm, row_numbers in duplicate_tracker.items()
            if len(row_numbers) > 1
        }
        for cd_cvm, row_numbers in sorted(duplicate_codes.items()):
            report["duplicate_cd_cvm_rows"].append(
                {"cd_cvm": cd_cvm, "row_numbers": row_numbers}
            )
        parsed_rows = [row for row in raw_valid_rows if row.cd_cvm not in duplicate_codes]

    report["source_values_found"] = sorted({row.source for row in parsed_rows})
    report["as_of_date_values_found"] = sorted({row.as_of_date for row in parsed_rows})
    return parsed_rows


def _company_indexes(company_rows: dict[int, dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    indexes = {"cnpj": {}, "ticker": {}, "company_name": {}}
    for row in company_rows.values():
        compact = {
            "cd_cvm": int(row["cd_cvm"]),
            "company_name": row.get("company_name"),
            "ticker_b3": row.get("ticker_b3"),
            "cnpj": row.get("cnpj"),
        }
        cnpj = _normalize_cnpj(row.get("cnpj"))
        ticker = _normalize_ticker(row.get("ticker_b3"))
        name = _normalize_name(row.get("company_name"))
        if cnpj:
            indexes["cnpj"].setdefault(cnpj, []).append(compact)
        if ticker:
            indexes["ticker"].setdefault(ticker, []).append(compact)
        if name:
            indexes["company_name"].setdefault(name, []).append(compact)
    return indexes


def _fallback_diagnostics(mapping: MappingRow, indexes: dict[str, dict[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    lookups = {
        "cnpj": _normalize_cnpj(mapping.cnpj),
        "ticker": _normalize_ticker(mapping.ticker),
        "company_name": _normalize_name(mapping.company_name),
    }
    for key, value in lookups.items():
        if not value:
            continue
        matches = indexes[key].get(value, [])
        if matches:
            diagnostics.append({"key": key, "value": value, "possible_matches": matches})
    return diagnostics


def _compare_optional_identifiers(mapping: MappingRow, company: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if mapping.cnpj and _normalize_cnpj(mapping.cnpj) != _normalize_cnpj(company.get("cnpj")):
        warnings.append("cnpj_mismatch")
    if mapping.ticker and _normalize_ticker(mapping.ticker) != _normalize_ticker(company.get("ticker_b3")):
        warnings.append("ticker_mismatch")
    if mapping.company_name and _normalize_name(mapping.company_name) != _normalize_name(company.get("company_name")):
        warnings.append("company_name_mismatch")
    return warnings


def _build_update_plan(
    mappings: list[MappingRow],
    company_rows: dict[int, dict[str, Any]],
    report: dict[str, Any],
) -> list[tuple[MappingRow, dict[str, Any]]]:
    indexes = _company_indexes(company_rows)
    update_plan: list[tuple[MappingRow, dict[str, Any]]] = []
    skipped: list[dict[str, Any]] = []
    matched_items: list[dict[str, Any]] = []
    unmatched_items: list[dict[str, Any]] = []

    for mapping in mappings:
        company = company_rows.get(mapping.cd_cvm)
        if company is None:
            diagnostics = _fallback_diagnostics(mapping, indexes)
            unmatched = mapping.to_report()
            unmatched["possible_fallback_matches"] = diagnostics
            unmatched_items.append(unmatched)
            if diagnostics:
                report["fallback_key_diagnostics"].append(
                    {
                        "row_number": mapping.row_number,
                        "cd_cvm": mapping.cd_cvm,
                        "diagnostics_only": True,
                        "matches": diagnostics,
                    }
                )
            skipped.append(
                {
                    "cd_cvm": mapping.cd_cvm,
                    "row_number": mapping.row_number,
                    "reason": "cd_cvm_not_found_in_companies",
                }
            )
            continue

        identifier_warnings = _compare_optional_identifiers(mapping, company)
        matched_items.append(
            {
                "cd_cvm": mapping.cd_cvm,
                "row_number": mapping.row_number,
                "company_name": company.get("company_name"),
                "current_gics_sector": company.get("gics_sector"),
                "current_gics_sub_industry": company.get("gics_sub_industry"),
                "new_gics_sector": mapping.gics_sector,
                "new_gics_sub_industry": mapping.gics_sub_industry,
                "identifier_warnings": identifier_warnings,
            }
        )
        update_plan.append((mapping, company))

    report["matched_companies"] = {"count": len(matched_items), "items": matched_items}
    report["unmatched_mappings"] = {"count": len(unmatched_items), "items": unmatched_items}
    report["companies_skipped"]["items"].extend(skipped)
    return update_plan


def _update_projection(
    company_rows: dict[int, dict[str, Any]],
    update_plan: list[tuple[MappingRow, dict[str, Any]]],
) -> dict[int, dict[str, Any]]:
    projected = {cd_cvm: dict(row) for cd_cvm, row in company_rows.items()}
    for mapping, _company in update_plan:
        projected[mapping.cd_cvm]["gics_sector"] = mapping.gics_sector
        projected[mapping.cd_cvm]["gics_sub_industry"] = mapping.gics_sub_industry
        projected[mapping.cd_cvm]["gics_sector_slug"] = sector_slugify(mapping.gics_sector)
    return projected


def _state_summary(
    company_rows: dict[int, dict[str, Any]],
    report: dict[str, Any],
    trusted_mappings: list[MappingRow] | None = None,
) -> None:
    current_sector_values = sorted(
        {
            str(row.get("gics_sector")).strip()
            for row in company_rows.values()
            if _clean(row.get("gics_sector"))
        }
    )
    current_sub_values = sorted(
        {
            str(row.get("gics_sub_industry")).strip()
            for row in company_rows.values()
            if _clean(row.get("gics_sub_industry"))
        }
    )
    report["current_db_gics_field_counts"] = {
        "companies_with_gics_sector_field": sum(1 for row in company_rows.values() if _clean(row.get("gics_sector"))),
        "companies_with_gics_sub_industry_field": sum(
            1 for row in company_rows.values() if _clean(row.get("gics_sub_industry"))
        ),
        "distinct_gics_sector_field_values": current_sector_values,
        "distinct_gics_sub_industry_field_values": current_sub_values,
        "note": "Valores fisicos atuais podem ser untrusted durante recovery; import modes usam cobertura do CSV aprovado.",
    }

    if trusted_mappings is not None:
        trusted_by_code = {mapping.cd_cvm: mapping for mapping in trusted_mappings if mapping.cd_cvm in company_rows}
        unclassified = [
            {
                "cd_cvm": int(row["cd_cvm"]),
                "company_name": row.get("company_name"),
                "ticker_b3": row.get("ticker_b3"),
            }
            for cd_cvm, row in company_rows.items()
            if cd_cvm not in trusted_by_code
        ]
        report["companies_still_unclassified"] = {
            "count": len(unclassified),
            "sample": sorted(unclassified, key=lambda row: str(row.get("company_name") or ""))[:25],
            "basis": "companies not covered by approved mapping file",
        }
        report["distinct_gics_sectors_after_import"] = sorted(
            {mapping.gics_sector for mapping in trusted_by_code.values()}
        )
        report["distinct_gics_sub_sectors_after_import"] = sorted(
            {mapping.gics_sub_industry for mapping in trusted_by_code.values()}
        )
        return

    unclassified = [
        {
            "cd_cvm": int(row["cd_cvm"]),
            "company_name": row.get("company_name"),
            "ticker_b3": row.get("ticker_b3"),
        }
        for row in company_rows.values()
        if not _clean(row.get("gics_sector"))
    ]
    report["companies_still_unclassified"] = {
        "count": len(unclassified),
        "sample": sorted(unclassified, key=lambda row: str(row.get("company_name") or ""))[:25],
        "basis": "current physical DB fields",
    }
    report["distinct_gics_sectors_after_import"] = sorted(
        {
            str(row.get("gics_sector")).strip()
            for row in company_rows.values()
            if _clean(row.get("gics_sector"))
        }
    )
    report["distinct_gics_sub_sectors_after_import"] = sorted(
        {
            str(row.get("gics_sub_industry")).strip()
            for row in company_rows.values()
            if _clean(row.get("gics_sub_industry"))
        }
    )


def _apply_updates(engine, update_plan: list[tuple[MappingRow, dict[str, Any]]], columns: set[str]) -> list[dict[str, Any]]:
    set_parts = ["gics_sector = :gics_sector", "gics_sub_industry = :gics_sub_industry"]
    if "gics_sector_slug" in columns:
        set_parts.append("gics_sector_slug = :gics_sector_slug")
    update_sql = text(
        f"""
        UPDATE companies
        SET {', '.join(set_parts)}
        WHERE cd_cvm = :cd_cvm
        """
    )
    updated: list[dict[str, Any]] = []
    with engine.begin() as conn:
        for mapping, company in update_plan:
            old_sector = _clean(company.get("gics_sector"))
            old_sub = _clean(company.get("gics_sub_industry"))
            old_slug = _clean(company.get("gics_sector_slug"))
            new_slug = sector_slugify(mapping.gics_sector)
            if old_sector == mapping.gics_sector and old_sub == mapping.gics_sub_industry and (
                "gics_sector_slug" not in columns or old_slug == new_slug
            ):
                continue
            conn.execute(
                update_sql,
                {
                    "cd_cvm": mapping.cd_cvm,
                    "gics_sector": mapping.gics_sector,
                    "gics_sub_industry": mapping.gics_sub_industry,
                    "gics_sector_slug": new_slug,
                },
            )
            updated.append(
                {
                    "cd_cvm": mapping.cd_cvm,
                    "company_name": company.get("company_name"),
                    "old_gics_sector": old_sector,
                    "old_gics_sub_industry": old_sub,
                    "new_gics_sector": mapping.gics_sector,
                    "new_gics_sub_industry": mapping.gics_sub_industry,
                    "source": mapping.source,
                    "as_of_date": mapping.as_of_date,
                }
            )
    return updated


def _reload_company_state(engine) -> dict[int, dict[str, Any]]:
    with engine.connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT cd_cvm, company_name, ticker_b3, cnpj,
                           gics_sector, gics_sector_slug, gics_sub_industry
                    FROM companies
                    ORDER BY cd_cvm
                    """
                )
            ).mappings().all()
        ]
    return {int(row["cd_cvm"]): row for row in rows}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa GICS aprovado de data/import/gics_mapping.csv para companies.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Grava as atualizacoes aprovadas no banco.")
    mode.add_argument("--check", action="store_true", help="Apenas checa schema/contagens; nao exige CSV.")
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=DEFAULT_MAPPING_PATH,
        help="CSV aprovado de GICS. Padrao: data/import/gics_mapping.csv",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Arquivo JSON de relatorio. Padrao: data/reports/gics_backfill_report.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode = "check" if args.check else "apply" if args.apply else "dry-run"
    mapping_path = args.mapping_file.resolve()
    report_path = args.report_file.resolve()
    report = _base_report(mode, mapping_path, report_path)

    settings = build_settings(project_root=ROOT)
    engine = build_engine(settings)
    company_rows, company_columns = _load_company_rows(engine, report)
    if report["errors"]:
        report["status"] = "schema_error"
        _write_report(report, report_path)
        print(f"Erro: {report['errors'][-1]}")
        print(f"Relatorio: {report_path}")
        return 3

    if args.check:
        _state_summary(company_rows, report)
        report["status"] = "check_completed"
        _write_report(report, report_path)
        print("Sanity check concluido; nenhuma linha foi alterada.")
        print(f"Relatorio: {report_path}")
        return 0

    mappings = _read_mapping_file(mapping_path, report)
    if report["status"] in {"missing_mapping_file", "invalid_mapping_file"}:
        _state_summary(company_rows, report, trusted_mappings=[])
        _write_report(report, report_path)
        print(f"Erro: {report['errors'][-1]}")
        print(f"Relatorio: {report_path}")
        return 2

    update_plan = _build_update_plan(mappings, company_rows, report)
    duplicate_skips = [
        {"cd_cvm": item["cd_cvm"], "row_numbers": item["row_numbers"], "reason": "duplicate_cd_cvm"}
        for item in report["duplicate_cd_cvm_rows"]
    ]
    invalid_skips = [
        {"row_number": item["row_number"], "cd_cvm": item.get("cd_cvm"), "reason": "invalid_row", "errors": item["errors"]}
        for item in report["invalid_rows"]
    ]
    report["companies_skipped"]["items"].extend(duplicate_skips)
    report["companies_skipped"]["items"].extend(invalid_skips)

    if args.apply:
        updated = _apply_updates(engine, update_plan, company_columns)
        report["companies_updated"] = {"count": len(updated), "items": updated}
        unchanged = [
            {
                "cd_cvm": mapping.cd_cvm,
                "row_number": mapping.row_number,
                "reason": "already_same",
            }
            for mapping, company in update_plan
            if _clean(company.get("gics_sector")) == mapping.gics_sector
            and _clean(company.get("gics_sub_industry")) == mapping.gics_sub_industry
            and (
                "gics_sector_slug" not in company_columns
                or _clean(company.get("gics_sector_slug")) == sector_slugify(mapping.gics_sector)
            )
        ]
        report["companies_skipped"]["items"].extend(unchanged)
        final_state = _reload_company_state(engine)
        report["status"] = "applied"
    else:
        would_update = []
        dry_run_skips = []
        for mapping, company in update_plan:
            new_slug = sector_slugify(mapping.gics_sector)
            same = (
                _clean(company.get("gics_sector")) == mapping.gics_sector
                and _clean(company.get("gics_sub_industry")) == mapping.gics_sub_industry
                and (
                    "gics_sector_slug" not in company_columns
                    or _clean(company.get("gics_sector_slug")) == new_slug
                )
            )
            item = {
                "cd_cvm": mapping.cd_cvm,
                "row_number": mapping.row_number,
                "company_name": company.get("company_name"),
                "old_gics_sector": company.get("gics_sector"),
                "old_gics_sub_industry": company.get("gics_sub_industry"),
                "new_gics_sector": mapping.gics_sector,
                "new_gics_sub_industry": mapping.gics_sub_industry,
                "source": mapping.source,
                "as_of_date": mapping.as_of_date,
            }
            if same:
                dry_run_skips.append({**item, "reason": "already_same"})
            else:
                would_update.append(item)
        report["companies_would_update"] = {"count": len(would_update), "items": would_update}
        report["companies_skipped"]["items"].extend(dry_run_skips)
        final_state = _update_projection(company_rows, update_plan)
        report["status"] = "dry_run_completed"

    report["companies_skipped"]["count"] = len(report["companies_skipped"]["items"])
    trusted_mappings = [mapping for mapping, _company in update_plan]
    _state_summary(final_state if args.apply else company_rows, report, trusted_mappings=trusted_mappings)
    _write_report(report, report_path)

    print(f"Modo: {mode}")
    print(f"Mapeamentos lidos: {report['mappings_read']}")
    print(f"Invalidos: {len(report['invalid_rows'])}")
    print(f"Duplicados: {len(report['duplicate_cd_cvm_rows'])}")
    print(f"Empresas encontradas por cd_cvm: {report['matched_companies']['count']}")
    print(f"Mapeamentos sem empresa: {report['unmatched_mappings']['count']}")
    if args.apply:
        print(f"Empresas atualizadas: {report['companies_updated']['count']}")
    else:
        print(f"Empresas que seriam atualizadas: {report['companies_would_update']['count']}")
    print(f"Ainda sem GICS: {report['companies_still_unclassified']['count']}")
    print(f"Relatorio: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
