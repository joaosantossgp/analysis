from __future__ import annotations

import importlib.abc
import sys
from contextlib import contextmanager

import pytest

from src.platform.api_errors import NotFoundError
from src.financials.read_service import CVMReadService


class _ForbiddenImportFinder(importlib.abc.MetaPathFinder):
    def __init__(self, prefixes: tuple[str, ...]) -> None:
        self.prefixes = prefixes

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
        if any(
            fullname == prefix or fullname.startswith(f"{prefix}.")
            for prefix in self.prefixes
        ):
            raise AssertionError(f"forbidden import in desktop runtime path: {fullname}")
        return None


@contextmanager
def _forbid_imports(*prefixes: str):
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    }
    for name in saved:
        sys.modules.pop(name, None)
    finder = _ForbiddenImportFinder(tuple(prefixes))
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        for name in list(sys.modules):
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_request_company_refresh_raises_shared_not_found_without_fastapi_imports():
    service = object.__new__(CVMReadService)
    service._ensure_company_catalog_metadata = lambda cd_cvm: False
    service._resolve_refresh_range = lambda *, start_year, end_year: (
        start_year,
        end_year or 2026,
    )
    service.get_company_info = lambda cd_cvm: None

    with _forbid_imports("apps.api", "fastapi"):
        with pytest.raises(NotFoundError, match="cd_cvm=999999"):
            service.request_company_refresh(999999, start_year=2025, end_year=2025)
