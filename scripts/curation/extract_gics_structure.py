"""Extract the current GICS hierarchy (codes and names only) from the GICS Map workbook.

Development tool for the GICS curation pipeline (#519). The workbook is a curation
input and is not committed; only codes and names are written to the repo.
Discontinued codes are struck through in the workbook and are excluded.

Usage: python scripts/curation/extract_gics_structure.py "<path to GICS Map xlsx>"
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import openpyxl

OUTPUT = Path(__file__).resolve().parents[2] / "data" / "reference" / "gics_structure.csv"
GICS_VERSION = "2023 structure (definitions 2025-02)"
EXPECTED_COUNTS = {2: 11, 4: 25, 6: 74, 8: 163}
_ANNOTATION = re.compile(r"\s*\((?:[^)]*\b(?:new|code|change|definition|update|name)\b[^)]*)\)", re.IGNORECASE)


def clean_name(raw: object) -> str:
    text = " ".join(str(raw).split())
    text = _ANNOTATION.sub("", text)
    return text.replace("*", "").strip()


def extract(workbook_path: str) -> dict[str, str]:
    sheet = openpyxl.load_workbook(workbook_path, data_only=True).worksheets[0]
    names: dict[str, str] = {}
    for row in sheet.iter_rows():
        for cell in row:
            value = cell.value
            if not isinstance(value, (int, float)) or cell.font.strike:
                continue
            code = str(int(value))
            if len(code) not in EXPECTED_COUNTS:
                continue
            name_cell = sheet.cell(cell.row, cell.column + 1)
            if name_cell.value and not name_cell.font.strike:
                names[code] = clean_name(name_cell.value)
    return names


def build_rows(names: dict[str, str]) -> list[dict[str, str]]:
    counts = {size: sum(1 for c in names if len(c) == size) for size in EXPECTED_COUNTS}
    if counts != EXPECTED_COUNTS:
        raise SystemExit(f"Unexpected GICS level counts {counts}, expected {EXPECTED_COUNTS}")
    rows = []
    for sub in sorted(c for c in names if len(c) == 8):
        parents = [sub[:2], sub[:4], sub[:6]]
        missing = [p for p in parents if p not in names]
        if missing:
            raise SystemExit(f"Sub-industry {sub} has no parent {missing}")
        rows.append({
            "sector_code": sub[:2], "sector": names[sub[:2]],
            "industry_group_code": sub[:4], "industry_group": names[sub[:4]],
            "industry_code": sub[:6], "industry": names[sub[:6]],
            "sub_industry_code": sub, "sub_industry": names[sub],
            "gics_version": GICS_VERSION,
        })
    return rows


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = build_rows(extract(sys.argv[1]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} sub-industries to {OUTPUT}")


if __name__ == "__main__":
    main()
