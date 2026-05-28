from __future__ import annotations

import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_XLS_FILE = REPO_ROOT / "output" / "reports" / "PETROBRAS_financials.xlsx"


def resolve_xlsx_path(
    xlsx_arg: str | None,
    *,
    legacy_filename: str = "PETROBRAS_financials.xlsx",
) -> Path:
    if xlsx_arg:
        candidate = Path(xlsx_arg)
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Arquivo informado em --xlsx nao encontrado: {candidate}")

    legacy_xls_file = REPO_ROOT / "output" / legacy_filename
    if DEFAULT_XLS_FILE.exists():
        return DEFAULT_XLS_FILE
    if legacy_xls_file.exists():
        return legacy_xls_file

    raise FileNotFoundError(
        "Nao foi encontrado arquivo padrao. Esperado em "
        f"{DEFAULT_XLS_FILE} (ou legado {legacy_xls_file})."
    )


def add_xlsx_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--xlsx",
        help="Caminho do arquivo XLSX de saida (padrao: output/reports/PETROBRAS_financials.xlsx)",
    )
