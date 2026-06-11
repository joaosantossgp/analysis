from __future__ import annotations

from typing import Any, Optional

# Centralized formula definitions
# Maps: target_id -> (list of dependency target_ids, list of required dependency target_ids)
# If a dependency is NOT in the required list, it is optional (treated as 0.0 if not mapped at all).
FORMULA_DEFS_INDUSTRIAL = {
    "DRE:3.03": (["DRE:3.01", "DRE:3.02"], ["DRE:3.01", "DRE:3.02"]),
    "DRE:3.06": (["DRE:3.06.01", "DRE:3.06.02"], []),
    "DRE:3.05": (["DRE:3.03", "DRE:3.04"], ["DRE:3.03"]),
    "DRE:3.07": (["DRE:3.05", "DRE:3.06"], ["DRE:3.05"]),
    "DRE:3.09": (["DRE:3.07", "DRE:3.08"], ["DRE:3.07"]),
    "DRE:3.11": (["DRE:3.09", "DRE:3.10"], ["DRE:3.09"]),
    "BPA:1": (["BPA:1.01", "BPA:1.02"], ["BPA:1.01", "BPA:1.02"]),
    "BPP:2": (["BPP:2.01", "BPP:2.02", "BPP:2.03"], ["BPP:2.01", "BPP:2.02", "BPP:2.03"]),
    "DFC:6.01": (["DFC:6.01.01", "DFC:6.01.02", "DFC:6.01.03"], ["DFC:6.01.01", "DFC:6.01.02"]),
    "DFC:6.05": (["DFC:6.01", "DFC:6.02", "DFC:6.03", "DFC:6.04"], ["DFC:6.01"]),
}

FORMULA_DEFS_FINANCIAL = {
    "DRE:3.03": (["DRE:3.01", "DRE:3.02"], ["DRE:3.01", "DRE:3.02"]),
    "DRE:3.05": (["DRE:3.03", "DRE:3.04"], ["DRE:3.03"]),
    "DRE:3.06": (["DRE:3.06.01", "DRE:3.06.02"], []),
    # In financials, 3.09 is Net Income (Consolidated) = Pre-tax Income (3.05) + Income Tax (3.06)
    "DRE:3.09": (["DRE:3.05", "DRE:3.06"], ["DRE:3.05"]),
    "DRE:3.11": (["DRE:3.09", "DRE:3.10"], ["DRE:3.09"]),
    "DFC:6.01": (["DFC:6.01.01", "DFC:6.01.02", "DFC:6.01.03"], ["DFC:6.01.01", "DFC:6.01.02"]),
    "DFC:6.05": (["DFC:6.01", "DFC:6.02", "DFC:6.03", "DFC:6.04"], ["DFC:6.01"]),
}

# The canonical evaluation order for formulas (topological sort)
FORMULA_EVAL_ORDER = [
    "BPA:1",
    "BPP:2",
    "DFC:6.01",
    "DFC:6.05",
    "DRE:3.03",
    "DRE:3.06",
    "DRE:3.05",
    "DRE:3.07",
    "DRE:3.09",
    "DRE:3.11",
]


def get_formula_definitions(is_financial: bool) -> dict[str, dict[str, Any]]:
    """Exposes formula definitions to both backend and frontend."""
    defs = FORMULA_DEFS_FINANCIAL if is_financial else FORMULA_DEFS_INDUSTRIAL
    result = {}
    for target_id, (deps, reqs) in defs.items():
        result[target_id] = {
            "dependencies": deps,
            "required": reqs,
        }
    return result


def is_formula_row(target_id: str, is_financial: bool) -> bool:
    defs = FORMULA_DEFS_FINANCIAL if is_financial else FORMULA_DEFS_INDUSTRIAL
    return target_id in defs


def evaluate_formulas(
    is_financial: bool,
    entries: list[Any],
    periods: list[str],
    values_by_target_period: dict[str, dict[str, float | None]],
    tolerance: float = 1.0,
) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, dict[str, Any]]], list[Any]]:
    """Evaluates formulas in topological order.

    Returns:
        1. updated values_by_target_period (calculated values filled in)
        2. check_statuses: target_id -> period -> check status dict
        3. list of validation issue payloads (dict representation of MappingValidationIssue)
    """
    from src.financials.excel_mapping import MappingValidationIssue

    defs = get_formula_definitions(is_financial)
    active_target_ids = {entry.target_id for entry in entries}
    entries_by_id = {entry.target_id: entry for entry in entries}

    check_statuses: dict[str, dict[str, dict[str, Any]]] = {}
    validation_issues = []

    # Initialize check_statuses for all formula targets
    for target_id in defs:
        check_statuses[target_id] = {}

    # We evaluate period by period to ensure independent calculations
    for period in periods:
        for target_id in FORMULA_EVAL_ORDER:
            if target_id not in defs or target_id not in active_target_ids:
                continue

            formula_def = defs[target_id]
            deps = formula_def["dependencies"]
            reqs = formula_def["required"]

            # Calculate calculated value
            missing_dep = False
            calculated_sum = 0.0
            
            for dep_id in deps:
                # Is this dependency mapped or present?
                dep_entry = entries_by_id.get(dep_id)
                dep_has_sources = bool(dep_entry.sources) if dep_entry else False

                if dep_id not in values_by_target_period:
                    # Dep is not even in values, treat as unmapped
                    if dep_id in reqs:
                        missing_dep = True
                        break
                    else:
                        continue

                dep_val = values_by_target_period[dep_id].get(period)
                if dep_val is None:
                    if dep_has_sources or (dep_id in reqs):
                        # If mapped but missing, or if required, it is missing
                        missing_dep = True
                        break
                    else:
                        # Optional unmapped/empty treated as 0.0
                        dep_val = 0.0

                calculated_sum += dep_val

            # Store computed value or None
            values_by_target_period.setdefault(target_id, {})
            
            reported_val = None
            # If the formula row itself has mapped CVM sources, we get the reported CVM value.
            # However, during evaluation, we store the *calculated* value in the main slot.
            entry = entries_by_id.get(target_id)
            if entry and entry.sources:
                # We fetch what the query layer resolved originally for this row (before we overwrite it).
                # Wait! Let's check how the caller provides values_by_target_period.
                # The caller populated values_by_target_period with the direct query results.
                # So values_by_target_period[target_id][period] contains the reported CVM value!
                reported_val = values_by_target_period[target_id].get(period)

            if missing_dep:
                values_by_target_period[target_id][period] = None
                check_statuses[target_id][period] = {
                    "status": "unavailable",
                    "variance": None,
                    "reported_value": reported_val,
                }
            else:
                values_by_target_period[target_id][period] = calculated_sum

                if reported_val is not None:
                    variance = calculated_sum - reported_val
                    abs_var = abs(variance)
                    if abs_var <= 1e-7:
                        status = "pass"
                    elif abs_var <= tolerance:
                        status = "rounding_difference"
                    else:
                        status = "mismatch"
                        # Generate validation issue if mismatch
                        validation_issues.append(
                            MappingValidationIssue(
                                severity="warning",
                                code="calculated_mismatch",
                                message=(
                                    f"Calculated subtotal for {entry.target_label} ({calculated_sum:.2f} R$ mm) "
                                    f"does not match reported CVM value ({reported_val:.2f} R$ mm) in {period}. "
                                    f"Variance: {variance:+.2f} R$ mm."
                                ),
                                target_id=target_id,
                            )
                        )
                    check_statuses[target_id][period] = {
                        "status": status,
                        "variance": variance,
                        "reported_value": reported_val,
                    }
                else:
                    check_statuses[target_id][period] = {
                        "status": "calculated",
                        "variance": None,
                        "reported_value": None,
                    }

    return values_by_target_period, check_statuses, validation_issues
