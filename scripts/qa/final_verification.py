"""Final verification for historical bug fixes."""

from __future__ import annotations

import argparse

import pandas as pd

from workbook_paths import add_xlsx_argument, resolve_xlsx_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Final verification for known bug fixes")
    add_xlsx_argument(parser)
    args = parser.parse_args()
    xls_file = resolve_xlsx_path(args.xlsx, legacy_filename="PETROBRAS_financials_1.xlsx")

    print("=" * 80)
    print("FINAL VERIFICATION: ALL 4 BUGS")
    print("=" * 80)
    print(f"Arquivo analisado: {xls_file}")

    print("\n[BUG #1] YEAR COVERAGE")
    print("-" * 80)
    bpp = pd.read_excel(xls_file, sheet_name="BPP", header=2, index_col=[0, 1])
    year_cols = sorted([c for c in bpp.columns if c.isdigit()])
    q25_cols = [c for c in bpp.columns if "25" in str(c)]
    print(f"Full years (annual data): {year_cols}")
    print(f"2025 quarterly columns: {q25_cols}")
    if len(q25_cols) >= 3:
        print("STATUS: PASS - 2025 Q1/Q2/Q3 are present")
    else:
        print("STATUS: FAIL - 2025 data missing")

    print("\n[BUG #2] BPP QUARTERLY REPLICATION")
    print("-" * 80)
    row = bpp.iloc[0]
    test_data = {
        "1Q24": row["1Q24"],
        "2Q24": row["2Q24"],
        "3Q24": row["3Q24"],
        "2024": row["2024"],
    }
    print(f"Sample account: {bpp.index[0]}")
    print(f"Values: {test_data}")
    unique_vals = len(set([v for v in test_data.values() if pd.notna(v)]))
    if unique_vals > 1:
        print("STATUS: PASS - Quarterly values are distinct")
    else:
        print("STATUS: FAIL - Values are still replicated")

    print("\n[BUG #3] BPA TOTALS CONSISTENCY")
    print("-" * 80)
    bpa = pd.read_excel(xls_file, sheet_name="BPA", header=2, index_col=[0, 1])
    total_2024 = bpa.loc[("1", slice(None)), "2024"].iloc[0]
    circ_2024 = bpa.loc[("1.01", slice(None)), "2024"].iloc[0]
    naocirc_2024 = bpa.loc[("1.02", slice(None)), "2024"].iloc[0]
    diff = abs(total_2024 - (circ_2024 + naocirc_2024))

    print(f"Total Assets (1):        {total_2024:>15,.0f}")
    print(f"Circulante (1.01):       {circ_2024:>15,.0f}")
    print(f"Nao-Circulante (1.02):   {naocirc_2024:>15,.0f}")
    print(f"Sum (1.01 + 1.02):       {circ_2024 + naocirc_2024:>15,.0f}")
    print(f"Difference:              {diff:>15,.2f}")
    if diff < 0.01:
        print("STATUS: PASS - Totals match perfectly")
    else:
        print(f"STATUS: FAIL - Difference of {diff:,.2f} million")

    print("\n[BUG #4] RECORTE CONSISTENCY")
    print("-" * 80)
    with pd.ExcelFile(xls_file) as xls:
        all_consolidated = True
        for sheet in ["BPA", "BPP", "DRE", "DFC"]:
            df_header = pd.read_excel(xls, sheet_name=sheet, nrows=1, header=None)
            header_text = str(df_header.iloc[0, 0])
            is_cons = "Consolidated" in header_text or "consolidated" in header_text
            print(f"{sheet}: {header_text[:50]}")
            if not is_cons:
                all_consolidated = False

        if all_consolidated:
            print("STATUS: PASS - All sheets show Consolidated")
        else:
            print("STATUS: FAIL - Mixed or incorrect recorte")

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print("All critical bugs have been verified against the generated output.")
    print(f"File: {xls_file.name}")


if __name__ == "__main__":
    main()
