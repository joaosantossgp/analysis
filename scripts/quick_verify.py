"""Quick verification checks for generated Excel output."""

from __future__ import annotations

import argparse

import pandas as pd

from workbook_paths import add_xlsx_argument, resolve_xlsx_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick verification checks for output workbook")
    add_xlsx_argument(parser)
    args = parser.parse_args()
    xls_file = resolve_xlsx_path(args.xlsx)

    print(f"Arquivo analisado: {xls_file}")

    print("1. Checking DS_CONTA_norm in BPA...")
    bpa = pd.read_excel(xls_file, sheet_name="BPA", header=2)
    print(f"Columns (first 15): {list(bpa.columns[:15])}")
    print(f"DS_CONTA_norm present: {'DS_CONTA_norm' in bpa.columns}")

    if "DS_CONTA_norm" in bpa.columns:
        print("\nSample rows:")
        id_col = "LINE_ID" if "LINE_ID" in bpa.columns else "LINE_ID_BASE"
        print(bpa[[id_col, "DS_CONTA", "DS_CONTA_norm"]].head(3))

    print("\n\n2. Checking DRE duplicates...")
    dre = pd.read_excel(xls_file, sheet_name="DRE", header=2)
    id_col = "LINE_ID" if "LINE_ID" in dre.columns else "LINE_ID_BASE"
    line_id_counts = dre[id_col].value_counts()
    dups = line_id_counts[line_id_counts > 1]

    if len(dups) > 0:
        print(f"FAIL: Found {len(dups)} duplicate {id_col}s")
        for dup_id in dups.index[:2]:
            print(f"\n  {id_col}: '{dup_id}'")
    else:
        print("PASS: No duplicates in DRE")

    print("\n3. Checking all sheets...")
    for sheet in ["BPA", "BPP", "DRE", "DFC"]:
        df = pd.read_excel(xls_file, sheet_name=sheet, header=2)
        id_col = "LINE_ID" if "LINE_ID" in df.columns else "LINE_ID_BASE"
        dups = df[id_col].value_counts()
        dups = dups[dups > 1]
        status = "PASS" if len(dups) == 0 else f"FAIL ({len(dups)} dups)"
        print(f"  {sheet}: {status}")


if __name__ == "__main__":
    main()
