from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

DEFAULT_MAPPING_VERSION = "model-mapping-v1"
SYSTEM_DEFAULT_PRESET_ID = "system:default"
VALID_MAPPING_OPERATIONS = frozenset({"direct", "sum", "sum_with_sign"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ModelMappingSource:
    statement_type: str
    line_id_base: str
    cd_conta: str | None = None
    label_snapshot: str | None = None
    sign: int = 1
    position: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ModelMappingSource":
        sign = -1 if int(payload.get("sign") or 1) < 0 else 1
        return cls(
            statement_type=str(payload.get("statement_type") or "").upper(),
            line_id_base=str(payload.get("line_id_base") or "").strip(),
            cd_conta=_clean_optional(payload.get("cd_conta")),
            label_snapshot=_clean_optional(payload.get("label_snapshot")),
            sign=sign,
            position=int(payload.get("position") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement_type": self.statement_type,
            "line_id_base": self.line_id_base,
            "cd_conta": self.cd_conta,
            "label_snapshot": self.label_snapshot,
            "sign": int(self.sign),
            "position": int(self.position),
        }


@dataclass(frozen=True)
class ModelMappingEntry:
    target_id: str
    target_label: str
    group: str
    statement_type: str
    display_order: int
    indent_level: int = 0
    required: bool = False
    operation: str = "direct"
    is_subtotal: bool = False
    sources: tuple[ModelMappingSource, ...] = field(default_factory=tuple)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ModelMappingEntry":
        operation = str(payload.get("operation") or "direct")
        sources = tuple(
            sorted(
                (
                    ModelMappingSource.from_payload(source)
                    for source in payload.get("sources", [])
                    if isinstance(source, dict)
                ),
                key=lambda source: source.position,
            )
        )
        return cls(
            target_id=str(payload.get("target_id") or "").strip(),
            target_label=str(payload.get("target_label") or "").strip(),
            group=str(payload.get("group") or "").strip(),
            statement_type=str(payload.get("statement_type") or "").upper(),
            display_order=int(payload.get("display_order") or 0),
            indent_level=int(payload.get("indent_level") or 0),
            required=bool(payload.get("required")),
            operation=operation,
            is_subtotal=bool(payload.get("is_subtotal")),
            sources=sources,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_label": self.target_label,
            "group": self.group,
            "statement_type": self.statement_type,
            "display_order": int(self.display_order),
            "indent_level": int(self.indent_level),
            "required": bool(self.required),
            "operation": self.operation,
            "is_subtotal": bool(self.is_subtotal),
            "sources": [source.to_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class ModelMappingDefinition:
    preset_id: str
    name: str
    description: str | None
    origin: str
    default_mapping_version: str
    sector_tags: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None
    validation_status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    entries: tuple[ModelMappingEntry, ...] = field(default_factory=tuple)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ModelMappingDefinition":
        entries = tuple(
            sorted(
                (
                    ModelMappingEntry.from_payload(entry)
                    for entry in payload.get("entries", [])
                    if isinstance(entry, dict)
                ),
                key=lambda entry: entry.display_order,
            )
        )
        raw_tags = payload.get("sector_tags") or []
        sector_tags = tuple(str(tag).strip() for tag in raw_tags if str(tag).strip())
        return cls(
            preset_id=str(payload.get("preset_id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            description=_clean_optional(payload.get("description")),
            origin=str(payload.get("origin") or "user").strip() or "user",
            default_mapping_version=str(
                payload.get("default_mapping_version") or DEFAULT_MAPPING_VERSION
            ),
            sector_tags=sector_tags,
            notes=_clean_optional(payload.get("notes")),
            validation_status=_clean_optional(payload.get("validation_status")),
            created_at=_clean_optional(payload.get("created_at")),
            updated_at=_clean_optional(payload.get("updated_at")),
            entries=entries,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "name": self.name,
            "description": self.description,
            "origin": self.origin,
            "default_mapping_version": self.default_mapping_version,
            "sector_tags": list(self.sector_tags),
            "notes": self.notes,
            "validation_status": self.validation_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class MappingValidationIssue:
    severity: str
    code: str
    message: str
    target_id: str | None = None
    source_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "target_id": self.target_id,
            "source_id": self.source_id,
        }


def ensure_excel_mapping_tables_for_connection(conn: Any) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS excel_mapping_presets (
                preset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                origin TEXT NOT NULL,
                default_mapping_version TEXT NOT NULL,
                sector_tags TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                validation_status TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS excel_mapping_entries (
                preset_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                target_label TEXT NOT NULL,
                group_name TEXT NOT NULL,
                statement_type TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                indent_level INTEGER NOT NULL DEFAULT 0,
                required INTEGER NOT NULL DEFAULT 0,
                operation TEXT NOT NULL,
                is_subtotal INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (preset_id, target_id)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS excel_mapping_sources (
                preset_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                statement_type TEXT NOT NULL,
                line_id_base TEXT NOT NULL,
                cd_conta TEXT,
                label_snapshot TEXT,
                sign INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (preset_id, target_id, position)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS excel_mapping_company_defaults (
                cd_cvm INTEGER PRIMARY KEY,
                preset_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_excel_mapping_presets_name
            ON excel_mapping_presets(name)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_excel_mapping_sources_line
            ON excel_mapping_sources(statement_type, line_id_base)
            """
        )
    )


def system_default_preset_summary(
    *,
    company_default: bool = False,
) -> dict[str, Any]:
    return {
        "preset_id": SYSTEM_DEFAULT_PRESET_ID,
        "name": "Default",
        "description": "System default model mapping shipped with CVMAnalytics.",
        "origin": "system",
        "default_mapping_version": DEFAULT_MAPPING_VERSION,
        "sector_tags": [],
        "notes": None,
        "validation_status": None,
        "created_at": None,
        "updated_at": None,
        "company_default": bool(company_default),
    }


def make_user_preset_id() -> str:
    return f"user:{uuid.uuid4().hex}"


class ExcelMappingRepository:
    def __init__(self, engine: Any):
        self.engine = engine

    def list_presets(self, *, company_default_preset_id: str | None = None) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            ensure_excel_mapping_tables_for_connection(conn)
            rows = conn.execute(
                text(
                    """
                    SELECT preset_id, name, description, origin,
                           default_mapping_version, sector_tags, notes,
                           validation_status, created_at, updated_at
                    FROM excel_mapping_presets
                    ORDER BY lower(name), preset_id
                    """
                )
            ).mappings().all()
        presets = [
            system_default_preset_summary(
                company_default=company_default_preset_id in (None, SYSTEM_DEFAULT_PRESET_ID)
            )
        ]
        for row in rows:
            preset_id = str(row["preset_id"])
            presets.append(
                {
                    "preset_id": preset_id,
                    "name": row["name"],
                    "description": row.get("description"),
                    "origin": row["origin"],
                    "default_mapping_version": row["default_mapping_version"],
                    "sector_tags": _loads_list(row.get("sector_tags")),
                    "notes": row.get("notes"),
                    "validation_status": row.get("validation_status"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "company_default": preset_id == company_default_preset_id,
                }
            )
        return presets

    def load_preset(self, preset_id: str) -> ModelMappingDefinition | None:
        if preset_id == SYSTEM_DEFAULT_PRESET_ID:
            return None
        with self.engine.begin() as conn:
            ensure_excel_mapping_tables_for_connection(conn)
            preset = conn.execute(
                text(
                    """
                    SELECT preset_id, name, description, origin,
                           default_mapping_version, sector_tags, notes,
                           validation_status, created_at, updated_at
                    FROM excel_mapping_presets
                    WHERE preset_id = :preset_id
                    """
                ),
                {"preset_id": preset_id},
            ).mappings().first()
            if preset is None:
                return None
            entry_rows = conn.execute(
                text(
                    """
                    SELECT preset_id, target_id, target_label, group_name,
                           statement_type, display_order, indent_level,
                           required, operation, is_subtotal
                    FROM excel_mapping_entries
                    WHERE preset_id = :preset_id
                    ORDER BY display_order, target_id
                    """
                ),
                {"preset_id": preset_id},
            ).mappings().all()
            source_rows = conn.execute(
                text(
                    """
                    SELECT preset_id, target_id, position, statement_type,
                           line_id_base, cd_conta, label_snapshot, sign
                    FROM excel_mapping_sources
                    WHERE preset_id = :preset_id
                    ORDER BY target_id, position
                    """
                ),
                {"preset_id": preset_id},
            ).mappings().all()

        sources_by_target: dict[str, list[ModelMappingSource]] = {}
        for row in source_rows:
            source = ModelMappingSource(
                statement_type=str(row["statement_type"]),
                line_id_base=str(row["line_id_base"]),
                cd_conta=_clean_optional(row.get("cd_conta")),
                label_snapshot=_clean_optional(row.get("label_snapshot")),
                sign=-1 if int(row.get("sign") or 1) < 0 else 1,
                position=int(row.get("position") or 0),
            )
            sources_by_target.setdefault(str(row["target_id"]), []).append(source)

        entries = []
        for row in entry_rows:
            target_id = str(row["target_id"])
            entries.append(
                ModelMappingEntry(
                    target_id=target_id,
                    target_label=str(row["target_label"]),
                    group=str(row["group_name"]),
                    statement_type=str(row["statement_type"]),
                    display_order=int(row["display_order"]),
                    indent_level=int(row.get("indent_level") or 0),
                    required=bool(row.get("required")),
                    operation=str(row["operation"]),
                    is_subtotal=bool(row.get("is_subtotal")),
                    sources=tuple(sources_by_target.get(target_id, [])),
                )
            )

        return ModelMappingDefinition(
            preset_id=str(preset["preset_id"]),
            name=str(preset["name"]),
            description=_clean_optional(preset.get("description")),
            origin=str(preset["origin"]),
            default_mapping_version=str(preset["default_mapping_version"]),
            sector_tags=tuple(_loads_list(preset.get("sector_tags"))),
            notes=_clean_optional(preset.get("notes")),
            validation_status=_clean_optional(preset.get("validation_status")),
            created_at=_clean_optional(preset.get("created_at")),
            updated_at=_clean_optional(preset.get("updated_at")),
            entries=tuple(entries),
        )

    def save_preset(self, mapping: ModelMappingDefinition) -> ModelMappingDefinition:
        preset_id = mapping.preset_id
        if not preset_id or preset_id == SYSTEM_DEFAULT_PRESET_ID or preset_id.startswith("system:"):
            preset_id = make_user_preset_id()
        now = utc_now_iso()
        existing = self.load_preset(preset_id)
        created_at = existing.created_at if existing and existing.created_at else now
        normalized = ModelMappingDefinition(
            preset_id=preset_id,
            name=mapping.name or "Untitled mapping",
            description=mapping.description,
            origin="user",
            default_mapping_version=mapping.default_mapping_version or DEFAULT_MAPPING_VERSION,
            sector_tags=tuple(mapping.sector_tags),
            notes=mapping.notes,
            validation_status=mapping.validation_status,
            created_at=created_at,
            updated_at=now,
            entries=tuple(sorted(mapping.entries, key=lambda entry: entry.display_order)),
        )
        with self.engine.begin() as conn:
            ensure_excel_mapping_tables_for_connection(conn)
            conn.execute(
                text("DELETE FROM excel_mapping_sources WHERE preset_id = :preset_id"),
                {"preset_id": preset_id},
            )
            conn.execute(
                text("DELETE FROM excel_mapping_entries WHERE preset_id = :preset_id"),
                {"preset_id": preset_id},
            )
            conn.execute(
                text("DELETE FROM excel_mapping_presets WHERE preset_id = :preset_id"),
                {"preset_id": preset_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO excel_mapping_presets (
                        preset_id, name, description, origin,
                        default_mapping_version, sector_tags, notes,
                        validation_status, created_at, updated_at
                    )
                    VALUES (
                        :preset_id, :name, :description, :origin,
                        :default_mapping_version, :sector_tags, :notes,
                        :validation_status, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "preset_id": normalized.preset_id,
                    "name": normalized.name,
                    "description": normalized.description,
                    "origin": normalized.origin,
                    "default_mapping_version": normalized.default_mapping_version,
                    "sector_tags": json.dumps(list(normalized.sector_tags), ensure_ascii=True),
                    "notes": normalized.notes,
                    "validation_status": normalized.validation_status,
                    "created_at": normalized.created_at,
                    "updated_at": normalized.updated_at,
                },
            )
            for entry in normalized.entries:
                conn.execute(
                    text(
                        """
                        INSERT INTO excel_mapping_entries (
                            preset_id, target_id, target_label, group_name,
                            statement_type, display_order, indent_level,
                            required, operation, is_subtotal
                        )
                        VALUES (
                            :preset_id, :target_id, :target_label, :group_name,
                            :statement_type, :display_order, :indent_level,
                            :required, :operation, :is_subtotal
                        )
                        """
                    ),
                    {
                        "preset_id": normalized.preset_id,
                        "target_id": entry.target_id,
                        "target_label": entry.target_label,
                        "group_name": entry.group,
                        "statement_type": entry.statement_type,
                        "display_order": int(entry.display_order),
                        "indent_level": int(entry.indent_level),
                        "required": 1 if entry.required else 0,
                        "operation": entry.operation,
                        "is_subtotal": 1 if entry.is_subtotal else 0,
                    },
                )
                for position, source in enumerate(entry.sources):
                    conn.execute(
                        text(
                            """
                            INSERT INTO excel_mapping_sources (
                                preset_id, target_id, position, statement_type,
                                line_id_base, cd_conta, label_snapshot, sign
                            )
                            VALUES (
                                :preset_id, :target_id, :position, :statement_type,
                                :line_id_base, :cd_conta, :label_snapshot, :sign
                            )
                            """
                        ),
                        {
                            "preset_id": normalized.preset_id,
                            "target_id": entry.target_id,
                            "position": int(position),
                            "statement_type": source.statement_type,
                            "line_id_base": source.line_id_base,
                            "cd_conta": source.cd_conta,
                            "label_snapshot": source.label_snapshot,
                            "sign": -1 if source.sign < 0 else 1,
                        },
                    )
        loaded = self.load_preset(preset_id)
        if loaded is None:
            raise RuntimeError(f"Saved mapping preset {preset_id} could not be reloaded.")
        return loaded

    def get_company_default_preset_id(self, cd_cvm: int) -> str | None:
        with self.engine.begin() as conn:
            ensure_excel_mapping_tables_for_connection(conn)
            row = conn.execute(
                text(
                    """
                    SELECT preset_id
                    FROM excel_mapping_company_defaults
                    WHERE cd_cvm = :cd_cvm
                    """
                ),
                {"cd_cvm": int(cd_cvm)},
            ).mappings().first()
        return str(row["preset_id"]) if row else None

    def set_company_default_preset(self, cd_cvm: int, preset_id: str) -> None:
        now = utc_now_iso()
        with self.engine.begin() as conn:
            ensure_excel_mapping_tables_for_connection(conn)
            conn.execute(
                text(
                    """
                    DELETE FROM excel_mapping_company_defaults
                    WHERE cd_cvm = :cd_cvm
                    """
                ),
                {"cd_cvm": int(cd_cvm)},
            )
            if preset_id != SYSTEM_DEFAULT_PRESET_ID:
                conn.execute(
                    text(
                        """
                        INSERT INTO excel_mapping_company_defaults (
                            cd_cvm, preset_id, updated_at
                        )
                        VALUES (:cd_cvm, :preset_id, :updated_at)
                        """
                    ),
                    {
                        "cd_cvm": int(cd_cvm),
                        "preset_id": preset_id,
                        "updated_at": now,
                    },
                )


def _loads_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    try:
        loaded = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        loaded = []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if str(item).strip()]


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None
