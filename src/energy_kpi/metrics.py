"""Energy unit conversion helpers.

These functions are deliberately small and explicit: the plant-parcel layer
uses mixed source units (MW, MWmed, MWh, GWh), so conversion code must be easy
to audit and test.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime


def hours_in_month(year: int, month: int) -> int:
    """Return calendar hours in a month, including leap-year February."""
    if month < 1 or month > 12:
        raise ValueError(f"month must be 1..12, got {month!r}")
    return calendar.monthrange(int(year), int(month))[1] * 24


def hours_in_reference_month(reference_month: str | date | datetime) -> int:
    """Return hours for a reference month represented as YYYYMM or YYYY-MM."""
    year, month = parse_reference_month(reference_month)
    return hours_in_month(year, month)


def parse_reference_month(reference_month: str | date | datetime) -> tuple[int, int]:
    if isinstance(reference_month, datetime):
        return reference_month.year, reference_month.month
    if isinstance(reference_month, date):
        return reference_month.year, reference_month.month
    text = str(reference_month).strip()
    match = re.search(r"(?P<year>\d{4})\D?(?P<month>\d{2})", text)
    if not match:
        raise ValueError(f"invalid reference month: {reference_month!r}")
    year = int(match.group("year"))
    month = int(match.group("month"))
    if month < 1 or month > 12:
        raise ValueError(f"invalid reference month: {reference_month!r}")
    return year, month


def normalize_reference_month(reference_month: str | date | datetime) -> str:
    """Normalize a reference month to YYYY-MM."""
    year, month = parse_reference_month(reference_month)
    return f"{year:04d}-{month:02d}"


def mwh_to_gwh(value_mwh: float | int | None) -> float | None:
    return None if value_mwh is None else float(value_mwh) / 1_000.0


def mwh_to_twh(value_mwh: float | int | None) -> float | None:
    return None if value_mwh is None else float(value_mwh) / 1_000_000.0


def mwmed_to_mwh(value_mwmed: float | int | None, hours: int) -> float | None:
    if value_mwmed is None:
        return None
    return float(value_mwmed) * int(hours)


def mwh_to_mwmed(value_mwh: float | int | None, hours: int) -> float | None:
    if value_mwh is None or int(hours) <= 0:
        return None
    return float(value_mwh) / int(hours)


def capacity_factor(
    generated_mwh: float | int | None,
    capacity_mw: float | int | None,
    hours: int,
) -> float | None:
    """Return capacity factor as a ratio, or None when it is not computable."""
    if generated_mwh is None or capacity_mw is None:
        return None
    capacity = float(capacity_mw)
    if capacity <= 0 or int(hours) <= 0:
        return None
    return float(generated_mwh) / (capacity * int(hours))
