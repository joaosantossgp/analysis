"""Select reported durations before deriving additive financial quarters."""
from __future__ import annotations

import calendar
import hashlib
import json
import math

import pandas as pd

from src.financials.utils import normalize_account_name

_QUARTER_END_DAYS = {3: 31, 6: 30, 9: 30, 12: 31}


def _clean_observation_value(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()[:10]
    if isinstance(value, (str, int, bool)):
        return value
    return None if pd.isna(value) else value


def _parse_ymd_fast(raw, cache: dict[object, tuple[int, int, int] | None]) -> tuple[int, int, int] | None:
    if raw in cache:
        return cache[raw]
    parsed: tuple[int, int, int] | None = None
    if isinstance(raw, str):
        s = raw.strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            y_s, m_s, d_s = s[:4], s[5:7], s[8:10]
            if y_s.isdigit() and m_s.isdigit() and d_s.isdigit():
                y, m, d = int(y_s), int(m_s), int(d_s)
                if 1 <= m <= 12 and 1 <= d <= calendar.monthrange(y, m)[1]:
                    parsed = (y, m, d)
        if parsed is None and s:
            ts = pd.to_datetime(s, errors="coerce")
            if not pd.isna(ts):
                parsed = (ts.year, ts.month, ts.day)
    elif raw is not None:
        ts = pd.to_datetime(raw, errors="coerce")
        if not pd.isna(ts):
            parsed = (ts.year, ts.month, ts.day)
    cache[raw] = parsed
    return parsed


def is_per_share(statement: str, code: object) -> bool:
    return statement == "DRE" and (str(code) == "3.99" or str(code).startswith("3.99."))


def observation_unit(row: dict, statement: str) -> str:
    if is_per_share(statement, row.get("CD_CONTA")):
        return "BRL/share" if row.get("MOEDA") == "REAL" else f"{row.get('MOEDA') or 'unknown'}/share"
    currency, scale = row.get("MOEDA"), row.get("ESCALA_MOEDA")
    if currency == "REAL" and str(scale).upper() in {"MIL", "UNIDADE", "MILHÃO", "MILHAO", "MILLION"}:
        return "BRL thousands"
    return " ".join(str(x) for x in (currency, scale) if x) or "unknown"


def source_observations(frame: pd.DataFrame, statement: str) -> list[dict]:
    observations = []
    cols = list(frame.columns)
    col_lists = [frame[col].tolist() for col in cols]
    for values in zip(*col_lists):
        row = {key: _clean_observation_value(val) for key, val in zip(cols, values)}
        row["STATEMENT_TYPE"] = statement
        row.setdefault("RAW_VL_CONTA", str(row.get("VL_CONTA")))
        row["UNIT"] = observation_unit(row, statement)
        # File value text, filing version and duration remain part of source identity.
        identity = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
        row["observation_id"] = hashlib.sha256(identity.encode("utf8")).hexdigest()
        observations.append(row)
    return observations


def build_statement(frame: pd.DataFrame, statement: str, tolerance: float) -> tuple[pd.DataFrame, list[dict]]:
    observations = source_observations(frame, statement)
    events, cells, output = [], [], []
    stock = statement in {"BPA", "BPP"}
    all_line_sources: dict[str, list[dict]] = {}
    for observation in observations:
        all_line_sources.setdefault(str(observation["LINE_ID_BASE"]), []).append(observation)
    # Duration is kept until selection; YTD and standalone are never pivoted together.
    grouped: dict[tuple[str, int], list[dict]] = {}
    periods: dict[int, set[str]] = {}
    date_cache: dict[object, tuple[int, int, int] | None] = {}
    date_key = "DT_REFER" if stock else "DT_FIM_EXERC"
    for obs in observations:
        ymd = _parse_ymd_fast(obs.get(date_key), date_cache)
        if ymd is None:
            continue
        year, month, day = ymd
        if _QUARTER_END_DAYS.get(month) != day:
            continue
        label = str(year) if month == 12 else f"{month // 3}Q{year % 100:02}"
        grouped.setdefault((str(obs["LINE_ID_BASE"]), year), []).append(obs)
        periods.setdefault(year, set()).add(label)
        if month == 12 and not stock:
            periods[year].add(f"4Q{year % 100:02}")

    # Compute normalized names and line-level identity ambiguity once per line_id
    # instead of re-scanning all_line_sources on every (line_id, year) iteration.
    norm_cache: dict[str, str] = {}

    def _norm(raw_text: object) -> str:
        key = str(raw_text or "")
        cached = norm_cache.get(key)
        if cached is None:
            cached = normalize_account_name(key)
            norm_cache[key] = cached
        return cached

    ambiguous_by_line: dict[str, bool] = {}
    for line_id, line_sources in all_line_sources.items():
        identities = {
            (
                str(s.get("CD_CONTA")),
                _norm(s.get("DS_CONTA")),
                s.get("REPORT_TYPE"),
                s.get("GRUPO_DFP"),
                s["UNIT"],
            )
            for s in line_sources
        }
        ambiguous_by_line[line_id] = len(identities) > 1

    sorted_periods_by_year = {year: sorted(p_set) for year, p_set in periods.items()}

    by_line: dict[str, dict] = {}
    for (line_id, year), sources in grouped.items():
        first = sources[0]
        result = by_line.get(line_id)
        if result is None:
            result = {
                "LINE_ID_BASE": line_id,
                "CD_CONTA": first.get("CD_CONTA"),
                "DS_CONTA": first.get("DS_CONTA"),
                "DS_CONTA_norm": _norm(first.get("DS_CONTA")),
                "QA_CONFLICT": False,
            }
            by_line[line_id] = result
        ambiguous_identity = ambiguous_by_line[line_id]
        nonadditive = is_per_share(statement, first.get("CD_CONTA"))

        # Pre-index this (line_id, year)'s observations by duration key.
        if stock:
            indexed_stock: dict[str, list[dict]] = {}
            for s in sources:
                indexed_stock.setdefault(str(s.get("DT_REFER"))[:10], []).append(s)
        else:
            indexed_flow: dict[tuple[str, str], list[dict]] = {}
            for s in sources:
                indexed_flow.setdefault(
                    (str(s.get("DT_INI_EXERC"))[:10], str(s.get("DT_FIM_EXERC"))[:10]),
                    [],
                ).append(s)

        def event(kind, period, inputs, **details):
            events.append(dict(
                type=kind, statement=statement, cd_cvm=first.get("CD_CVM"),
                line_id_base=line_id, cd_conta=first.get("CD_CONTA"),
                description=first.get("DS_CONTA"), year=year, period=period,
                # Observations are stored once in financial_source_observations; QA reads resolve ids (#583).
                unit=first["UNIT"], source_ids=[s["observation_id"] for s in inputs],
                action="Review the original filing and required period inputs; refresh explicitly after resolving source comparability.",
                **details,
            ))

        def candidates(start, end):
            if stock:
                return indexed_stock.get(end, [])
            return indexed_flow.get((start, end), [])

        def select(matches):
            unique = {s["observation_id"]: s for s in matches}
            # Duplicate observations may be identical; distinct versions are not interchangeable.
            comparable = {(s.get("VERSAO"), s.get("VL_CONTA"), s.get("MOEDA"), s.get("ESCALA_MOEDA"))
                          for s in unique.values()}
            if len(comparable) != 1:
                return None
            chosen = next(iter(unique.values()))
            return chosen if chosen.get("VL_CONTA") is not None else None

        for period in sorted_periods_by_year[year]:
            annual = period.isdigit()
            quarter = 4 if annual else int(period[0])
            end_month = 3 * quarter
            end = f"{year}-{end_month:02}-{_QUARTER_END_DAYS[end_month]}"
            start = f"{year}-01-01" if annual or stock else f"{year}-{end_month - 2:02}-01"
            direct = candidates(start, end)
            inputs, value, status, formula = direct, float("nan"), "unavailable", None
            if ambiguous_identity:
                inputs = all_line_sources[line_id]
                event("ACCOUNT_IDENTITY_AMBIGUOUS", period, inputs)
            elif first["UNIT"] not in {"BRL thousands", "BRL/share"}:
                inputs = sources
                event("UNIT_UNAVAILABLE", period, inputs)
            elif direct and select(direct) is None:
                event("SOURCE_OBSERVATION_AMBIGUOUS", period, direct)
            elif direct:
                chosen = select(direct)
                value, inputs, status = float(chosen["VL_CONTA"]), direct, "reported"
            elif stock or annual or quarter == 1:
                event("MISSING_OBSERVATION", period, sources, missing_inputs=[period])
            elif nonadditive:
                event("NON_ADDITIVE_PERIOD", period, sources, missing_inputs=[f"reported {period}"])
            else:
                current = candidates(f"{year}-01-01", end)
                prev_month = end_month - 3
                previous = candidates(f"{year}-01-01", f"{year}-{prev_month:02}-{_QUARTER_END_DAYS[prev_month]}")
                inputs = current + previous
                current_row, previous_row = select(current), select(previous)
                if not current:
                    event("MISSING_OBSERVATION", period, sources, missing_inputs=[str(year) if quarter == 4 else period])
                elif (current and current_row is None) or (previous and previous_row is None):
                    event("SOURCE_OBSERVATION_AMBIGUOUS", period, inputs)
                elif not previous:
                    event("MISSING_PREDECESSOR", period, inputs, missing_inputs=[f"{quarter - 1}Q{year % 100:02}"])
                else:
                    value = float(current_row["VL_CONTA"]) - float(previous_row["VL_CONTA"])
                    status, formula = "calculated", "current YTD - previous YTD"
            result[period] = value
            cells.append(dict(line_id_base=line_id, period=period, year=year, statement=statement,
                              unit=first["UNIT"], status=status, formula=formula,
                              description=first.get("DS_CONTA"),
                              source_ids=[s["observation_id"] for s in inputs]))

        qs = [result.get(f"{q}Q{year % 100:02}", float("nan")) for q in range(1, 5)]
        annual_value = result.get(str(year), float("nan"))
        if not nonadditive and not stock and pd.notna(annual_value) and all(pd.notna(v) for v in qs):
            actual = sum(qs)
            if abs(actual - annual_value) > tolerance:
                event("DFC_VALIDATION_FAILED", str(year), sources,
                      expected=annual_value, actual=actual, diff=abs(actual - annual_value))
    output = list(by_line.values())
    result = pd.DataFrame(output)
    result.attrs["source_observations"] = observations
    result.attrs["value_lineage"] = cells
    return result, events
