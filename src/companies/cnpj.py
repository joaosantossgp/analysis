# -*- coding: utf-8 -*-
"""CNPJ validation and formatting utilities."""
from __future__ import annotations

import re


def validate_cnpj(value: str | None) -> bool:
    """Validate a Brazilian CNPJ number using standard check-digit validation."""
    if not value:
        return False

    # Remove known formatting characters
    cleaned = re.sub(r"[.\-/]", "", str(value)).strip()

    # Cleaned value must be exactly 14 digits
    if not re.match(r"^\d{14}$", cleaned):
        return False

    # Reject known invalid patterns (all same digits)
    if re.match(r"^(\d)\1{13}$", cleaned):
        return False

    digits = [int(d) for d in cleaned]

    # Validate first check digit
    multipliers1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum1 = sum(d * m for d, m in zip(digits[:12], multipliers1))
    rem1 = sum1 % 11
    expected_d13 = 0 if rem1 < 2 else 11 - rem1
    if digits[12] != expected_d13:
        return False

    # Validate second check digit
    multipliers2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum2 = sum(d * m for d, m in zip(digits[:13], multipliers2))
    rem2 = sum2 % 11
    expected_d14 = 0 if rem2 < 2 else 11 - rem2
    if digits[13] != expected_d14:
        return False

    return True


def format_cnpj(value: str | None) -> str:
    """Format a Brazilian CNPJ number.

    Standard format: 00.000.000/0000-00.
    Returns "Not available" for invalid values.
    """
    if not value:
        return "Not available"

    cleaned = re.sub(r"[.\-/]", "", str(value)).strip()

    if not validate_cnpj(cleaned):
        return "Not available"

    return f"{cleaned[0:2]}.{cleaned[2:5]}.{cleaned[5:8]}/{cleaned[8:12]}-{cleaned[12:14]}"
