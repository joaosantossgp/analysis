from __future__ import annotations

import heapq
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("desktop.storage_inventory")

CONTRACT_VERSION = 1
HISTORY_LIMIT = 90
TOP_N_LIMIT = 25
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60
LOW_FREE_PERCENT = 10.0
LOW_FREE_BYTES = 5 * 1024**3
CRITICAL_FREE_PERCENT = 3.0
CRITICAL_FREE_BYTES = 1 * 1024**3
LARGE_WAL_RATIO = 0.5


@dataclass(frozen=True)
class RootSpec:
    id: str
    label: str
    path: Path
    category_id: str
    category_label: str
    segment_id: str
    segment_label: str
    storage_type: str


class StorageInventoryManager:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._active: dict[str, Any] | None = None
        self._latest_memory: dict[str, Any] | None = None

    @property
    def snapshot_path(self) -> Path:
        return Path(self.settings.paths.metadata_dir) / "storage_inventory_v1.json"

    def latest(self) -> dict[str, Any]:
        active = self.status()
        snapshot = self._read_snapshot()
        if snapshot is None:
            return self._empty_inventory(active)
        snapshot["scan_status"] = active
        snapshot["is_cached"] = True
        snapshot["is_stale"] = self._is_stale(snapshot.get("scanned_at"))
        snapshot["scan_age_seconds"] = self._scan_age_seconds(snapshot.get("scanned_at"))
        return snapshot

    def start_scan(self, *, persist: bool = True) -> dict[str, Any]:
        with self._lock:
            if self._active and self._active.get("status") == "running":
                return {"started": False, "scan_status": dict(self._active), "error": "storage scan already running"}

            scan_id = uuid.uuid4().hex
            self._active = {
                "scan_id": scan_id,
                "status": "running",
                "started_at": _utc_now(),
                "finished_at": None,
                "elapsed_ms": None,
                "error": None,
            }
            thread = threading.Thread(
                target=self._run_scan_thread,
                args=(scan_id, bool(persist)),
                name=f"storage-inventory-{scan_id[:8]}",
                daemon=True,
            )
            thread.start()
            return {"started": True, "scan_status": dict(self._active), "inventory": self._read_snapshot()}

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._active is None:
                return {
                    "scan_id": None,
                    "status": "idle",
                    "started_at": None,
                    "finished_at": None,
                    "elapsed_ms": None,
                    "error": None,
                }
            return dict(self._active)

    def compact_summary(self) -> dict[str, Any]:
        latest = self.latest()
        return {
            "status": latest.get("status"),
            "generated_at": latest.get("generated_at"),
            "scanned_at": latest.get("scanned_at"),
            "is_cached": latest.get("is_cached", True),
            "is_stale": latest.get("is_stale", False),
            "scan_age_seconds": latest.get("scan_age_seconds"),
            "scan_status": latest.get("scan_status"),
            "logical_bytes_total": int(latest.get("logical_bytes_total") or 0),
            "file_count": int(latest.get("file_count") or 0),
            "directory_count": int(latest.get("directory_count") or 0),
            "skipped_count": int(latest.get("skipped_count") or 0),
            "largest_category": _largest(latest.get("categories") or []),
            "largest_segment": _largest(latest.get("segments") or []),
            "main_volume": (latest.get("volumes") or [None])[0],
            "growth": latest.get("growth") or {},
            "warnings": latest.get("warnings") or [],
            "errors": latest.get("errors") or [],
            "measurement_notes": latest.get("measurement_notes") or [],
        }

    def _run_scan_thread(self, scan_id: str, persist: bool) -> None:
        logger.info("storage inventory scan started: %s", scan_id)
        start = time.perf_counter()
        try:
            inventory = self.scan()
            inventory["scan_status"] = {
                "scan_id": scan_id,
                "status": "succeeded" if inventory.get("status") != "partial" else "partial",
                "started_at": self.status().get("started_at"),
                "finished_at": _utc_now(),
                "elapsed_ms": inventory.get("elapsed_ms"),
                "error": None,
            }
            if persist:
                self._write_snapshot(inventory)
            else:
                inventory["warnings"].append("Inventory was not persisted by request.")
                self._latest_memory = inventory
            with self._lock:
                self._active = inventory["scan_status"]
            logger.info(
                "storage inventory scan finished: %s files=%s bytes=%s skipped=%s elapsed_ms=%s",
                scan_id,
                inventory.get("file_count"),
                inventory.get("logical_bytes_total"),
                inventory.get("skipped_count"),
                inventory.get("elapsed_ms"),
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.error("storage inventory scan failed: %s", scan_id, exc_info=True)
            with self._lock:
                self._active = {
                    "scan_id": scan_id,
                    "status": "failed",
                    "started_at": self._active.get("started_at") if self._active else None,
                    "finished_at": _utc_now(),
                    "elapsed_ms": elapsed_ms,
                    "error": str(exc),
                }

    def scan(self) -> dict[str, Any]:
        started = _utc_now()
        start = time.perf_counter()
        roots, excluded = self._resolved_roots()
        ownership_specs = sorted(
            self._all_root_specs(),
            key=lambda spec: len(str(spec.path.resolve())),
            reverse=True,
        )
        categories: dict[str, dict[str, Any]] = {}
        segments: dict[str, dict[str, Any]] = {}
        databases = self._database_specs()
        db_by_path = {str(spec.path.resolve()).casefold(): spec for spec in databases}
        sidecar_map: dict[str, RootSpec] = {}
        for spec in databases:
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar_map[str(Path(f"{spec.path}{suffix}").resolve()).casefold()] = spec

        totals = {"logical_bytes": 0, "files": 0, "dirs": 0, "skipped": 0}
        errors: list[str] = []
        warnings: list[str] = []
        largest_heap: list[tuple[int, int, dict[str, Any]]] = []
        seq = 0
        scanned_roots: list[dict[str, Any]] = []

        for root in roots:
            root_payload = {
                "id": root.id,
                "label": root.label,
                "path": str(root.path),
                "exists": root.path.exists(),
                "category_id": root.category_id,
                "segment_id": root.segment_id,
                "logical_bytes": 0,
                "file_count": 0,
                "directory_count": 0,
                "skipped_count": 0,
            }
            scanned_roots.append(root_payload)
            if not root.path.exists():
                warnings.append(f"Managed root missing: {root.label}")
                continue
            for file_info in self._iter_files(root.path, errors):
                if file_info.get("type") == "dir":
                    totals["dirs"] += 1
                    root_payload["directory_count"] += 1
                    continue
                if file_info.get("type") == "skipped":
                    totals["skipped"] += 1
                    root_payload["skipped_count"] += 1
                    continue
                path = Path(file_info["path"])
                size = int(file_info["size"])
                owner = self._classify_path(path, root, ownership_specs)
                category_id = owner.category_id
                category_label = owner.category_label
                segment_id = owner.segment_id
                segment_label = owner.segment_label
                storage_type = owner.storage_type
                resolved_key = str(path.resolve()).casefold()
                if resolved_key in db_by_path:
                    category_id = "databases"
                    category_label = "Databases"
                    segment_id = db_by_path[resolved_key].segment_id
                    segment_label = db_by_path[resolved_key].segment_label
                    storage_type = "sqlite"
                elif resolved_key in sidecar_map:
                    category_id = "database_sidecars"
                    category_label = "Database sidecars"
                    segment_id = sidecar_map[resolved_key].segment_id
                    segment_label = sidecar_map[resolved_key].segment_label
                    storage_type = "sqlite-sidecar"

                totals["logical_bytes"] += size
                totals["files"] += 1
                root_payload["logical_bytes"] += size
                root_payload["file_count"] += 1
                _add_aggregate(categories, category_id, category_label, size, root.id, storage_type)
                _add_aggregate(segments, segment_id, segment_label, size, root.id, storage_type)
                seq += 1
                item = {
                    "path": str(path),
                    "name": path.name,
                    "logical_bytes": size,
                    "category_id": category_id,
                    "category_label": category_label,
                    "segment_id": segment_id,
                    "segment_label": segment_label,
                    "storage_type": storage_type,
                    "modified_at": _mtime_iso(path),
                }
                heapq.heappush(largest_heap, (size, seq, item))
                if len(largest_heap) > TOP_N_LIMIT:
                    heapq.heappop(largest_heap)

        database_payloads = [self._database_payload(spec) for spec in databases]
        volumes = self._volume_payloads([root.path for root in roots])
        backup_candidates = self._backup_candidates()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        total = int(totals["logical_bytes"])
        category_rows = _aggregate_rows(categories, total)
        segment_rows = _aggregate_rows(segments, total)
        largest_items = [item for _, _, item in sorted(largest_heap, key=lambda row: row[0], reverse=True)]
        status = self._storage_status(volumes, totals["skipped"], errors, started)
        warnings.extend(self._database_warnings(database_payloads))
        growth = self._growth(total)
        history = self._history_summary(total, started)

        return {
            "contract_version": CONTRACT_VERSION,
            "status": status,
            "generated_at": _utc_now(),
            "scanned_at": started,
            "is_cached": False,
            "is_stale": False,
            "scan_age_seconds": 0,
            "logical_bytes_total": total,
            "allocated_bytes_total": None,
            "file_count": int(totals["files"]),
            "directory_count": int(totals["dirs"]),
            "skipped_count": int(totals["skipped"]),
            "elapsed_ms": elapsed_ms,
            "roots": scanned_roots,
            "excluded_roots": excluded,
            "volumes": volumes,
            "categories": category_rows,
            "segments": segment_rows,
            "databases": database_payloads,
            "backup_candidates": backup_candidates,
            "largest_items": largest_items,
            "growth": growth,
            "history": history,
            "warnings": warnings,
            "errors": errors[:20],
            "measurement_notes": [
                "logical_bytes is the sum of filesystem file lengths.",
                "allocated_bytes_total is unavailable on this platform-neutral scanner.",
                "SQLite free-page bytes are internal reusable capacity, not immediately reclaimable disk space.",
                "The scanner does not read file contents, hash files, run VACUUM, checkpoint WAL files, or follow symlinks/junctions.",
            ],
            "performance": {
                "files_per_second": round((totals["files"] / (elapsed_ms / 1000)), 2) if elapsed_ms > 0 else totals["files"],
                "full_database_table_scans": False,
                "content_hashing": False,
            },
        }

    def _iter_files(self, root: Path, errors: list[str]):
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_symlink():
                                yield {"type": "skipped", "path": entry.path, "reason": "symlink"}
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                yield {"type": "dir", "path": entry.path}
                                stack.append(Path(entry.path))
                                continue
                            if entry.is_file(follow_symlinks=False):
                                stat = entry.stat(follow_symlinks=False)
                                yield {"type": "file", "path": entry.path, "size": int(stat.st_size)}
                        except OSError as exc:
                            errors.append(f"Skipped {entry.path}: {exc}")
                            yield {"type": "skipped", "path": entry.path, "reason": type(exc).__name__}
            except OSError as exc:
                errors.append(f"Skipped {current}: {exc}")
                yield {"type": "skipped", "path": str(current), "reason": type(exc).__name__}

    def _resolved_roots(self) -> tuple[list[RootSpec], list[dict[str, Any]]]:
        raw_roots = self._all_root_specs()
        resolved: list[tuple[RootSpec, Path]] = []
        excluded: list[dict[str, Any]] = []
        seen: set[str] = set()
        for spec in raw_roots:
            rp = spec.path.resolve()
            key = str(rp).casefold()
            if key in seen:
                excluded.append({"id": spec.id, "path": str(spec.path), "reason": "duplicate_root"})
                continue
            nested_parent = next((parent for _, parent in resolved if _is_relative_to(rp, parent)), None)
            if nested_parent is not None:
                excluded.append({"id": spec.id, "path": str(spec.path), "reason": f"nested under {nested_parent}"})
                continue
            resolved.append((RootSpec(spec.id, spec.label, rp, spec.category_id, spec.category_label, spec.segment_id, spec.segment_label, spec.storage_type), rp))
            seen.add(key)
        return [spec for spec, _ in resolved], excluded

    def _all_root_specs(self) -> list[RootSpec]:
        p = self.settings.paths
        return [
            RootSpec("data", "Data root", Path(p.data_dir), "uncategorized", "Uncategorized managed data", "shared_metadata", "Shared metadata", "mixed"),
            RootSpec("db", "Database directory", Path(p.db_dir), "databases", "Databases", "shared_databases", "Shared databases", "sqlite"),
            RootSpec("input", "Input directory", Path(p.input_dir), "manual_imports", "Manual imports", "user_imports", "User imports", "files"),
            RootSpec("raw", "Raw source files", Path(p.raw_dir), "raw_sources", "Raw sources", "cvm_financials", "CVM financial statements", "files"),
            RootSpec("processed", "Processed input files", Path(p.processed_dir), "processed", "Processed data", "cvm_financials", "CVM financial statements", "files"),
            RootSpec("output", "Outputs and exports", Path(p.output_dir), "exports_reports", "Exports and reports", "outputs", "Generated outputs", "files"),
            RootSpec("reports", "Reports", Path(p.reports_dir), "exports_reports", "Exports and reports", "outputs", "Generated outputs", "files"),
            RootSpec("logs", "Logs", Path(p.logs_dir), "logs", "Logs", "shared_metadata", "Shared metadata", "logs"),
            RootSpec("cache", "Cache", Path(p.cache_dir), "cache", "Cache", "market_data", "Market data", "cache"),
            RootSpec("metadata", "Metadata", Path(p.metadata_dir), "metadata", "Metadata", "shared_metadata", "Shared metadata", "files"),
            RootSpec("analytics", "Analytical stores", Path(p.data_dir) / "analytics", "analytical_stores", "Analytical stores", "analytical_stores", "Local analytical stores", "mixed"),
            RootSpec("energy_hourly_store", "Energy hourly hot/cold store", Path(p.data_dir) / "analytics" / "energy" / "ccee_plant_generation_hourly", "analytical_stores", "Analytical stores", "energy_macro", "Energy macro / SIN / CCEE / Distribution", "mixed"),
            RootSpec("backup", "Backups and rollback", Path(p.data_dir) / "backup", "backups", "Backups and rollback", "local_backups", "Local backups", "files"),
            RootSpec("energy_raw", "Energy raw sources", Path(p.energy_kpi_raw_dir), "raw_sources", "Raw sources", "energy_macro", "Energy macro", "files"),
        ]

    @staticmethod
    def _classify_path(path: Path, fallback: RootSpec, ownership_specs: list[RootSpec]) -> RootSpec:
        resolved = path.resolve()
        for spec in ownership_specs:
            spec_path = spec.path.resolve()
            if resolved == spec_path or _is_relative_to(resolved, spec_path):
                return spec
        return fallback

    def _database_specs(self) -> list[RootSpec]:
        p = self.settings.paths
        specs = [
            RootSpec("cvm_financials", "CVM financials", Path(p.db_path), "databases", "Databases", "cvm_financials", "CVM financial statements", "sqlite"),
            RootSpec("energy_kpis", "Energy KPIs", Path(p.energy_kpi_db_path), "databases", "Databases", "energy_macro", "Energy macro / SIN / CCEE / Distribution", "sqlite"),
        ]
        news_db_path = getattr(p, "news_db_path", None)
        if news_db_path is not None:
            specs.append(RootSpec("news", "News", Path(news_db_path), "databases", "Databases", "news", "Financial news", "sqlite"))
        dedup: dict[str, RootSpec] = {}
        for spec in specs:
            dedup.setdefault(str(spec.path.resolve()).casefold(), spec)
        return list(dedup.values())

    def _database_payload(self, spec: RootSpec) -> dict[str, Any]:
        path = spec.path
        exists = path.exists()
        payload = {
            "id": spec.id,
            "label": spec.label,
            "path": str(path),
            "segment_id": spec.segment_id,
            "segment_label": spec.segment_label,
            "exists": exists,
            "readable": None,
            "logical_bytes": _file_size(path),
            "wal_bytes": _file_size(Path(f"{path}-wal")),
            "shm_bytes": _file_size(Path(f"{path}-shm")),
            "journal_bytes": _file_size(Path(f"{path}-journal")),
            "modified_at": _mtime_iso(path),
            "sqlite": None,
            "warnings": [],
        }
        if not exists:
            payload["readable"] = False
            payload["warnings"].append("Database file is missing.")
            return payload
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
            try:
                cur = conn.cursor()
                page_size = int(cur.execute("PRAGMA page_size").fetchone()[0] or 0)
                page_count = int(cur.execute("PRAGMA page_count").fetchone()[0] or 0)
                freelist_count = int(cur.execute("PRAGMA freelist_count").fetchone()[0] or 0)
                journal_mode = str(cur.execute("PRAGMA journal_mode").fetchone()[0] or "unknown")
                schema_version = int(cur.execute("PRAGMA schema_version").fetchone()[0] or 0)
                user_version = int(cur.execute("PRAGMA user_version").fetchone()[0] or 0)
                payload["readable"] = True
                payload["sqlite"] = {
                    "page_size": page_size,
                    "page_count": page_count,
                    "freelist_count": freelist_count,
                    "estimated_allocated_bytes": page_size * page_count,
                    "estimated_internal_free_bytes": page_size * freelist_count,
                    "journal_mode": journal_mode,
                    "schema_version": schema_version,
                    "user_version": user_version,
                }
            finally:
                conn.close()
        except Exception as exc:
            payload["readable"] = False
            payload["warnings"].append(f"SQLite metadata unavailable: {exc}")
        main_size = int(payload["logical_bytes"] or 0)
        wal_size = int(payload["wal_bytes"] or 0)
        if main_size > 0 and wal_size > main_size * LARGE_WAL_RATIO:
            payload["warnings"].append("WAL file is large relative to the main database. No checkpoint was run.")
        return payload

    def _volume_payloads(self, roots: list[Path]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        volumes: list[dict[str, Any]] = []
        for path in roots:
            anchor = path.anchor or str(path.resolve().anchor)
            key = anchor.casefold()
            if key in seen:
                continue
            seen.add(key)
            try:
                usage = shutil.disk_usage(path if path.exists() else path.parent)
                total = int(usage.total)
                free = int(usage.free)
                used = int(usage.used)
                free_pct = (free / total * 100) if total else None
                volumes.append({
                    "id": anchor,
                    "path": anchor,
                    "total_bytes": total,
                    "used_bytes": used,
                    "free_bytes": free,
                    "free_percent": free_pct,
                    "status": _volume_status(free, free_pct),
                })
            except Exception as exc:
                volumes.append({"id": anchor, "path": anchor, "error": str(exc), "status": "unknown"})
        return volumes

    def _storage_status(self, volumes: list[dict[str, Any]], skipped: int, errors: list[str], scanned_at: str) -> str:
        if any(volume.get("status") == "critical" for volume in volumes):
            return "critical"
        if errors:
            return "degraded"
        if skipped:
            return "degraded"
        if self._is_stale(scanned_at):
            return "degraded"
        if not volumes:
            return "unknown"
        if any(volume.get("status") == "degraded" for volume in volumes):
            return "degraded"
        return "healthy"

    @staticmethod
    def _database_warnings(databases: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        for db in databases:
            warnings.extend(f"{db.get('label')}: {warning}" for warning in db.get("warnings") or [])
        return warnings

    def _read_snapshot(self) -> dict[str, Any] | None:
        if self._latest_memory is not None:
            return dict(self._latest_memory)
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
            return None
        return payload

    def _write_snapshot(self, inventory: dict[str, Any]) -> None:
        path = self.snapshot_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(inventory)
        payload["history"] = self._updated_history(payload)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _updated_history(self, inventory: dict[str, Any]) -> list[dict[str, Any]]:
        previous = self._read_snapshot()
        history = list((previous or {}).get("history") or [])
        scanned_at = str(inventory.get("scanned_at") or _utc_now())
        day = scanned_at[:10]
        point = {
            "date": day,
            "scanned_at": scanned_at,
            "logical_bytes_total": int(inventory.get("logical_bytes_total") or 0),
            "file_count": int(inventory.get("file_count") or 0),
        }
        history = [row for row in history if row.get("date") != day]
        history.append(point)
        history.sort(key=lambda row: str(row.get("date") or ""))
        return history[-HISTORY_LIMIT:]

    def _history_summary(self, total: int, scanned_at: str) -> list[dict[str, Any]]:
        previous = self._read_snapshot()
        return list((previous or {}).get("history") or [])[-HISTORY_LIMIT:]

    def _growth(self, current_total: int) -> dict[str, Any]:
        previous = self._read_snapshot()
        history = list((previous or {}).get("history") or [])
        if not history:
            return {"available": False, "reason": "No previous storage snapshots."}
        prev = history[-1]
        return {
            "available": True,
            "previous_scanned_at": prev.get("scanned_at"),
            "change_since_previous_bytes": current_total - int(prev.get("logical_bytes_total") or 0),
            "seven_day_change_bytes": _change_since(history, current_total, 7),
            "thirty_day_change_bytes": _change_since(history, current_total, 30),
        }

    def _empty_inventory(self, active: dict[str, Any]) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": "unknown" if active.get("status") != "running" else "updating",
            "generated_at": _utc_now(),
            "scanned_at": None,
            "is_cached": True,
            "is_stale": True,
            "scan_age_seconds": None,
            "scan_status": active,
            "logical_bytes_total": 0,
            "allocated_bytes_total": None,
            "file_count": 0,
            "directory_count": 0,
            "skipped_count": 0,
            "elapsed_ms": None,
            "roots": [],
            "excluded_roots": [],
            "volumes": [],
            "categories": [],
            "segments": [],
            "databases": [],
            "largest_items": [],
            "backup_candidates": [],
            "growth": {"available": False, "reason": "No storage inventory has been created."},
            "history": [],
            "warnings": ["No storage inventory snapshot is available yet."],
            "errors": [],
            "measurement_notes": ["Open Storage and refresh inventory to create the first snapshot."],
        }

    def _backup_candidates(self) -> list[dict[str, Any]]:
        backup_root = Path(self.settings.paths.data_dir) / "backup"
        if not backup_root.exists():
            return []

        candidates: list[dict[str, Any]] = []
        try:
            entries = sorted(backup_root.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            return []

        for entry in entries:
            if entry.is_symlink() or not entry.exists():
                continue
            total = 0
            files = 0
            modified_at: str | None = _mtime_iso(entry)
            if entry.is_file():
                total = _file_size(entry)
                files = 1
            elif entry.is_dir():
                for file_info in self._iter_files(entry, []):
                    if file_info.get("type") != "file":
                        continue
                    path = Path(file_info["path"])
                    size = int(file_info.get("size") or 0)
                    total += size
                    files += 1
                    item_mtime = _mtime_iso(path)
                    if item_mtime and (modified_at is None or item_mtime > modified_at):
                        modified_at = item_mtime
            else:
                continue

            candidates.append({
                "id": entry.name,
                "label": _backup_candidate_label(entry.name),
                "path": str(entry),
                "logical_bytes": total,
                "file_count": files,
                "modified_at": modified_at,
                "reclaimable_bytes": total,
                "requires_confirmation": True,
                "destructive": True,
                "reason": "Rollback backup retained after a storage migration. Remove only after current data has been validated.",
            })

        candidates.sort(key=lambda row: int(row.get("logical_bytes") or 0), reverse=True)
        return candidates

    @staticmethod
    def _is_stale(scanned_at: Any) -> bool:
        age = StorageInventoryManager._scan_age_seconds(scanned_at)
        return age is None or age > STALE_AFTER_SECONDS

    @staticmethod
    def _scan_age_seconds(scanned_at: Any) -> int | None:
        if not scanned_at:
            return None
        try:
            dt = datetime.fromisoformat(str(scanned_at).replace("Z", "+00:00"))
            return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
        except Exception:
            return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return child != parent
    except ValueError:
        return False


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except OSError:
        return None


def _backup_candidate_label(name: str) -> str:
    if name.startswith("energy_kpis_swap_"):
        return "Energy KPI rollback backup"
    return name.replace("_", " ").strip() or "Rollback backup"


def _add_aggregate(rows: dict[str, dict[str, Any]], row_id: str, label: str, size: int, root_id: str, storage_type: str) -> None:
    row = rows.setdefault(row_id, {
        "id": row_id,
        "label": label,
        "logical_bytes": 0,
        "file_count": 0,
        "root_ids": set(),
        "storage_types": set(),
        "warnings": [],
    })
    row["logical_bytes"] += int(size)
    row["file_count"] += 1
    row["root_ids"].add(root_id)
    row["storage_types"].add(storage_type)


def _aggregate_rows(rows: dict[str, dict[str, Any]], total: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows.values():
        logical = int(row["logical_bytes"])
        result.append({
            "id": row["id"],
            "label": row["label"],
            "logical_bytes": logical,
            "allocated_bytes": None,
            "file_count": int(row["file_count"]),
            "percentage_of_total": (logical / total * 100) if total else 0,
            "root_ids": sorted(row["root_ids"]),
            "storage_types": sorted(row["storage_types"]),
            "warnings": list(row.get("warnings") or []),
        })
    result.sort(key=lambda item: int(item["logical_bytes"]), reverse=True)
    return result


def _largest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda item: int(item.get("logical_bytes") or 0))


def _volume_status(free_bytes: int, free_pct: float | None) -> str:
    pct = float(free_pct if free_pct is not None else 100.0)
    if free_bytes < CRITICAL_FREE_BYTES or pct < CRITICAL_FREE_PERCENT:
        return "critical"
    if free_bytes < LOW_FREE_BYTES or pct < LOW_FREE_PERCENT:
        return "degraded"
    return "healthy"


def _change_since(history: list[dict[str, Any]], current_total: int, days: int) -> int | None:
    if not history:
        return None
    cutoff = time.time() - days * 24 * 60 * 60
    candidate: dict[str, Any] | None = None
    for row in history:
        try:
            dt = datetime.fromisoformat(str(row.get("scanned_at")).replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.timestamp() <= cutoff:
            candidate = row
    if candidate is None:
        return None
    return current_total - int(candidate.get("logical_bytes_total") or 0)
