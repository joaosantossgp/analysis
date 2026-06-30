#!/usr/bin/env python3
"""Profile CVMAnalytics local storage without mutating user data."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.platform.settings import build_settings  # noqa: E402

SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
ANALYTIC_SUFFIXES = {".parquet", ".duckdb", ".arrow", ".feather"}
SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def _safe_stat(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError as exc:
        return {"path": str(path), "exists": False, "error": str(exc)}
    return {
        "path": str(path),
        "exists": True,
        "bytes": int(stat.st_size),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _iter_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _scan_files(root: Path, *, top_n: int) -> dict[str, Any]:
    totals_by_top_dir: dict[str, int] = {}
    suffix_totals: dict[str, int] = {}
    largest: list[dict[str, Any]] = []
    total = 0
    file_count = 0

    for path in _iter_files(root):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        file_count += 1
        total += int(size)
        rel = path.relative_to(root)
        top_dir = rel.parts[0] if rel.parts else path.name
        totals_by_top_dir[top_dir] = totals_by_top_dir.get(top_dir, 0) + int(size)
        suffix = path.suffix.lower() or "(none)"
        if any(str(path).lower().endswith(sidecar) for sidecar in SIDECAR_SUFFIXES):
            suffix = "(sqlite-sidecar)"
        suffix_totals[suffix] = suffix_totals.get(suffix, 0) + int(size)
        largest.append(
            {
                "path": str(path),
                "relative_path": str(rel),
                "bytes": int(size),
                "modified_at": _safe_stat(path).get("modified_at"),
            }
        )

    largest.sort(key=lambda item: int(item["bytes"]), reverse=True)
    return {
        "root": str(root),
        "exists": root.exists(),
        "total_bytes": total,
        "file_count": file_count,
        "top_level": [
            {"name": name, "bytes": size}
            for name, size in sorted(totals_by_top_dir.items(), key=lambda item: item[1], reverse=True)
        ],
        "suffixes": [
            {"suffix": suffix, "bytes": size}
            for suffix, size in sorted(suffix_totals.items(), key=lambda item: item[1], reverse=True)
        ],
        "largest_files": largest[:top_n],
    }


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _fetch_scalar(cur: sqlite3.Cursor, sql: str) -> Any:
    row = cur.execute(sql).fetchone()
    return row[0] if row else None


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _sqlite_profile(path: Path, *, include_dbstat: bool, include_integrity: bool) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        **_safe_stat(path),
        "type": "sqlite",
        "sidecars": {
            suffix.removeprefix("-"): _safe_stat(Path(f"{path}{suffix}"))
            for suffix in SIDECAR_SUFFIXES
        },
        "readable": False,
        "pragmas": {},
        "tables": [],
        "indexes": [],
        "dbstat": {"available": False, "objects": []},
        "checks": {},
        "elapsed_ms": None,
        "errors": [],
    }
    try:
        with _sqlite_readonly(path) as conn:
            cur = conn.cursor()
            payload["readable"] = True
            for pragma in ("page_size", "page_count", "freelist_count", "journal_mode", "schema_version", "user_version"):
                try:
                    payload["pragmas"][pragma] = _fetch_scalar(cur, f"PRAGMA {pragma}")
                except Exception as exc:  # pragma availability differs by SQLite build
                    payload["pragmas"][pragma] = {"error": str(exc)}
            page_size = int(payload["pragmas"].get("page_size") or 0)
            page_count = int(payload["pragmas"].get("page_count") or 0)
            freelist_count = int(payload["pragmas"].get("freelist_count") or 0)
            payload["pragmas"]["estimated_allocated_bytes"] = page_size * page_count
            payload["pragmas"]["estimated_internal_free_bytes"] = page_size * freelist_count

            object_rows = cur.execute(
                """
                SELECT name, type, tbl_name, sql
                FROM sqlite_master
                WHERE type IN ('table', 'index', 'view', 'trigger')
                ORDER BY type, name
                """
            ).fetchall()
            table_names = [
                str(row["name"])
                for row in object_rows
                if row["type"] == "table" and not str(row["name"]).startswith("sqlite_")
            ]
            for table_name in table_names:
                table_started = time.perf_counter()
                table_payload: dict[str, Any] = {
                    "name": table_name,
                    "row_count": None,
                    "row_count_elapsed_ms": None,
                    "columns": [],
                    "error": None,
                }
                try:
                    table_payload["row_count"] = int(
                        _fetch_scalar(cur, f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}") or 0
                    )
                    table_payload["row_count_elapsed_ms"] = round((time.perf_counter() - table_started) * 1000, 2)
                except Exception as exc:
                    table_payload["error"] = str(exc)
                try:
                    table_payload["columns"] = [
                        {
                            "cid": int(row[0]),
                            "name": str(row[1]),
                            "type": str(row[2] or ""),
                            "not_null": bool(row[3]),
                            "primary_key_position": int(row[5] or 0),
                        }
                        for row in cur.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
                    ]
                except Exception as exc:
                    table_payload["columns_error"] = str(exc)
                payload["tables"].append(table_payload)

                try:
                    for idx in cur.execute(f"PRAGMA index_list({_quote_identifier(table_name)})").fetchall():
                        index_name = str(idx[1])
                        columns = [
                            str(row[2])
                            for row in cur.execute(f"PRAGMA index_info({_quote_identifier(index_name)})").fetchall()
                        ]
                        payload["indexes"].append(
                            {
                                "table": table_name,
                                "name": index_name,
                                "unique": bool(idx[2]),
                                "origin": str(idx[3]),
                                "columns": columns,
                            }
                        )
                except Exception as exc:
                    payload["errors"].append(f"index list failed for {table_name}: {exc}")

            if include_dbstat:
                try:
                    payload["dbstat"] = {
                        "available": True,
                        "objects": [
                            {"name": str(row[0]), "bytes": int(row[1] or 0), "pages": int(row[2] or 0)}
                            for row in cur.execute(
                                """
                                SELECT name, SUM(pgsize) AS bytes, COUNT(*) AS pages
                                FROM dbstat
                                GROUP BY name
                                ORDER BY bytes DESC
                                LIMIT 100
                                """
                            ).fetchall()
                        ],
                    }
                except Exception as exc:
                    payload["dbstat"] = {"available": False, "error": str(exc), "objects": []}

            if include_integrity:
                for check_name, sql in (
                    ("quick_check", "PRAGMA quick_check"),
                    ("foreign_key_check", "PRAGMA foreign_key_check"),
                ):
                    check_started = time.perf_counter()
                    try:
                        rows = cur.execute(sql).fetchmany(20)
                        payload["checks"][check_name] = {
                            "elapsed_ms": round((time.perf_counter() - check_started) * 1000, 2),
                            "sample": [tuple(row) for row in rows],
                        }
                    except Exception as exc:
                        payload["checks"][check_name] = {"error": str(exc)}
    except Exception as exc:
        payload["errors"].append(str(exc))
    payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    payload["tables"].sort(key=lambda item: int(item.get("row_count") or 0), reverse=True)
    return payload


def _discover_stores(root: Path) -> list[Path]:
    if not root.exists():
        return []
    stores: list[Path] = []
    for path in _iter_files(root):
        lower = str(path).lower()
        if path.suffix.lower() in SQLITE_SUFFIXES | ANALYTIC_SUFFIXES:
            stores.append(path)
        elif any(lower.endswith(suffix) for suffix in SIDECAR_SUFFIXES):
            continue
    return sorted(set(stores), key=lambda item: str(item).lower())


def _profile_store(path: Path, *, include_dbstat: bool, include_integrity: bool) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in SQLITE_SUFFIXES:
        return _sqlite_profile(path, include_dbstat=include_dbstat, include_integrity=include_integrity)
    payload = _safe_stat(path)
    payload["type"] = suffix.removeprefix(".") or "file"
    return payload


def _markdown_report(profile: dict[str, Any]) -> str:
    lines = [
        "# CVMAnalytics Local Storage Profile",
        "",
        f"- Generated: `{profile['generated_at']}`",
        f"- Data root: `{profile['data_root']}`",
        f"- Total size: `{_format_bytes(profile['file_scan']['total_bytes'])}`",
        f"- File count: `{profile['file_scan']['file_count']}`",
        "",
        "## Top-Level Size",
        "",
        "| Path | Size |",
        "|---|---:|",
    ]
    for row in profile["file_scan"]["top_level"][:25]:
        lines.append(f"| `{row['name']}` | {_format_bytes(row['bytes'])} |")
    lines.extend(["", "## Largest Files", "", "| File | Size |", "|---|---:|"])
    for row in profile["file_scan"]["largest_files"]:
        lines.append(f"| `{row['relative_path']}` | {_format_bytes(row['bytes'])} |")
    lines.extend(["", "## Stores", ""])
    for store in profile["stores"]:
        lines.append(f"### `{store['path']}`")
        lines.append("")
        lines.append(f"- Type: `{store.get('type')}`")
        lines.append(f"- Size: `{_format_bytes(store.get('bytes'))}`")
        if store.get("type") == "sqlite":
            pragmas = store.get("pragmas") or {}
            lines.append(f"- Pages: `{pragmas.get('page_count')}` x `{pragmas.get('page_size')}`")
            lines.append(f"- Free pages: `{pragmas.get('freelist_count')}`")
            lines.append(f"- Journal mode: `{pragmas.get('journal_mode')}`")
            lines.append("")
            lines.append("| Largest tables by rows | Rows | Count time |")
            lines.append("|---|---:|---:|")
            for table in (store.get("tables") or [])[:20]:
                rows = table.get("row_count")
                elapsed = table.get("row_count_elapsed_ms")
                lines.append(f"| `{table['name']}` | {rows if rows is not None else 'n/a'} | {elapsed if elapsed is not None else 'n/a'} ms |")
            if (store.get("dbstat") or {}).get("available"):
                lines.append("")
                lines.append("| Largest SQLite objects by dbstat | Size | Pages |")
                lines.append("|---|---:|---:|")
                for obj in store["dbstat"]["objects"][:20]:
                    lines.append(f"| `{obj['name']}` | {_format_bytes(obj['bytes'])} | {obj['pages']} |")
        if store.get("errors"):
            lines.append("")
            lines.append("Errors:")
            for error in store["errors"]:
                lines.append(f"- {error}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_profile(
    *,
    data_root: Path | None,
    output_dir: Path | None,
    top_n: int,
    include_dbstat: bool,
    include_integrity: bool,
    write: bool,
) -> dict[str, Any]:
    settings = build_settings()
    resolved_root = (data_root or Path(settings.paths.data_dir)).expanduser().resolve()
    stores = [
        _profile_store(path, include_dbstat=include_dbstat, include_integrity=include_integrity)
        for path in _discover_stores(resolved_root)
    ]
    stores.sort(key=lambda item: int(item.get("bytes") or 0), reverse=True)
    profile = {
        "generated_at": _utc_now(),
        "data_root": str(resolved_root),
        "file_scan": _scan_files(resolved_root, top_n=top_n),
        "stores": stores,
    }
    if write:
        target_dir = (output_dir or (resolved_root / "metadata" / "storage_profiles")).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = profile["generated_at"].replace(":", "").replace("-", "")
        json_path = target_dir / f"storage_profile_{stamp}.json"
        md_path = target_dir / f"storage_profile_{stamp}.md"
        json_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(_markdown_report(profile), encoding="utf-8")
        profile["outputs"] = {"json": str(json_path), "markdown": str(md_path)}
    return profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile CVMAnalytics local storage read-only.")
    parser.add_argument("--data-root", help="Data root to profile. Defaults to configured CVMAnalytics data root.")
    parser.add_argument("--output-dir", help="Directory for JSON/Markdown outputs. Defaults to metadata/storage_profiles.")
    parser.add_argument("--top-n", type=int, default=50, help="Number of largest files to include.")
    parser.add_argument("--dbstat", action="store_true", help="Collect SQLite dbstat object sizes when available.")
    parser.add_argument("--integrity", action="store_true", help="Run SQLite quick_check and foreign_key_check.")
    parser.add_argument("--no-write", action="store_true", help="Print JSON only; do not write profile artifacts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = build_profile(
        data_root=Path(args.data_root) if args.data_root else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        top_n=max(1, int(args.top_n or 50)),
        include_dbstat=bool(args.dbstat),
        include_integrity=bool(args.integrity),
        write=not bool(args.no_write),
    )
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
