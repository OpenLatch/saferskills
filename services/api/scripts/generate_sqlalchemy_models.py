"""Generate SQLAlchemy ORM models from JSON Schema files with x-postgresql-* extensions.

Ported from openlatch-platform's `generate_sqlalchemy_models.py` and adapted for
SaferSkills:

* Output → `services/api/app/models/generated/`.
* `Base` is re-exported from `app.models.base` (one shared metadata with the
  hand-written internal models).
* Enums are **self-contained value tuples** (KNOWN_ENUMS carries `values`) — the
  generated `_base.py` emits `KIND_VALUES = (...)` + `kind_enum = sa.Enum(*KIND_VALUES,
  native_enum=True, create_type=False)`; columns are typed `Mapped[str]` (matches the
  hand-written models). No coupling to the Pydantic-generated enum classes.
* SaferSkills extensions over the OpenLatch generator:
  - `x-postgresql-classname` — ORM class name when it differs from the schema `title`
    (e.g. `scan-report.schema.json` title `ScanReport` → ORM class `Scan`).
  - `x-postgresql-nullable` — explicit nullability override (the plan's annotations
    assume it; the OpenLatch generator computed nullability purely from JSON Schema).
  - `metadata` property → attribute `item_metadata`, column name `"metadata"`
    (SQLAlchemy reserves `metadata` on declarative classes).
  - `maxLength` → `sa.String(n)`; `x-foreign-key.ondelete`; extra-column `length` /
    `unique` / `foreign_key` keys.
  - UUID columns → `PgUUID(as_uuid=True)` / `Mapped[UUID]`; date-time → `sa.DateTime`.

Usage:
    uv run python scripts/generate_sqlalchemy_models.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = SCRIPT_DIR.parent  # services/api/
REPO_ROOT = SERVICE_ROOT.parent.parent  # repo root
SCHEMAS_DIR = REPO_ROOT / "schemas"
TEMPLATES_DIR = SCRIPT_DIR / "templates"
OUTPUT_DIR = SERVICE_ROOT / "app" / "models" / "generated"

# Schemas that never back a DB table (rely on x-postgresql-skip otherwise).
EMBEDDED_SCHEMAS: set[str] = set()

# ---------------------------------------------------------------------------
# JSON Schema type -> SQLAlchemy column type mapping
# (json_type, format) -> SA column expression string
# ---------------------------------------------------------------------------
TYPE_MAP: dict[tuple[str, str | None], str] = {
    ("string", "uuid"): "PgUUID(as_uuid=True)",
    ("string", "date-time"): "sa.DateTime(timezone=True)",
    ("string", "date"): "sa.Date",
    ("string", "uri"): "sa.Text",
    ("string", None): "sa.Text",
    ("integer", None): "sa.Integer",
    ("number", None): "sa.Float(precision=24)",
    ("boolean", None): "sa.Boolean",
    ("object", None): "JSONB",
}

# JSON Schema type -> Python type annotation for Mapped[...]
MAPPED_TYPE_MAP: dict[tuple[str, str | None], str] = {
    ("string", "uuid"): "UUID",
    ("string", "date-time"): "datetime",
    ("string", "date"): "datetime",
    ("string", "uri"): "str",
    ("string", None): "str",
    ("integer", None): "int",
    ("number", None): "float",
    ("boolean", None): "bool",
    ("object", None): "dict[str, Any]",
}

# `x-postgresql-type` override — bypasses the JSON-Schema-derived type.
PG_TYPE_OVERRIDE_MAP: dict[str, tuple[str, str]] = {
    "BYTEA": ("sa.LargeBinary", "bytes"),
    "SMALLINT": ("sa.SmallInteger", "int"),
    # Force unbounded TEXT even when the wire schema carries a maxLength (e.g.
    # vendor_responses.body_markdown is TEXT + a CHECK, not VARCHAR(2000)).
    "TEXT": ("sa.Text", "str"),
}


# ---------------------------------------------------------------------------
# Data classes for template context
# ---------------------------------------------------------------------------
@dataclass
class EnumInfo:
    pg_name: str  # e.g. "kind"
    var_name: str  # e.g. "kind_enum"
    values_const: str  # e.g. "KIND_VALUES"
    values: tuple[str, ...]
    description: str


@dataclass
class ColumnInfo:
    name: str
    mapped_type: str
    column_args: list[str]


@dataclass
class ModelInfo:
    class_name: str
    tablename: str
    description: str
    columns: list[ColumnInfo]
    table_args: list[str] = field(default_factory=list)
    needs_jsonb: bool = False
    needs_datetime: bool = False
    needs_uuid: bool = False
    base_imports: str = ""  # extra imports from _base (enum vars)
    repr_string: str = ""


# ---------------------------------------------------------------------------
# KNOWN_ENUMS — the single closed-set source of truth.
#
# Each entry: {values: tuple, description: str}. Adding an enum to a schema
# requires adding an entry here in the same PR; the generator hard-fails on an
# unregistered x-postgresql-enum-type.
#
# These mirror the value tuples in the migration chain (0001 KIND_VALUES,
# TIER_VALUES, … + 0007/0008 visibility/source_kind/scan_run status). The
# internal hand-written tables item_sources.registry_id + rate_limits.bucket
# stay VARCHAR+CHECK and are NOT listed here (they are not generated).
# ---------------------------------------------------------------------------
KNOWN_ENUMS: dict[str, dict[str, Any]] = {
    "kind": {
        "values": ("skill", "mcp_server", "hook", "plugin", "rules"),
        "description": "PRD §2.2 artifact taxonomy.",
    },
    "popularity_tier": {
        "values": ("indexed", "lite", "deep", "on_demand"),
        "description": "PRD §6.2 scan-tier assignment.",
    },
    "tier": {
        "values": ("green", "yellow", "orange", "red", "unscoped"),
        "description": "Aggregate scan-result tier.",
    },
    "scan_source": {
        "values": ("submission", "ingestion", "rescan_drift", "rescan_appeal"),
        "description": "How the scan was triggered.",
    },
    "scan_run_status": {
        "values": ("pending", "running", "completed", "failed"),
        "description": "Repo-scan run lifecycle status.",
    },
    "severity": {
        "values": ("info", "low", "medium", "high", "critical"),
        "description": "5-tier severity ladder per D-02.",
    },
    "sub_score": {
        "values": ("security", "supply_chain", "maintenance", "transparency", "community"),
        "description": "5-axis sub-score per D-01.",
    },
    "status_at_scan": {
        "values": ("shadow", "active"),
        "description": "Rule status when finding emitted (D-14).",
    },
    "vendor_verification_state": {
        "values": ("pending", "verified", "expired", "revoked"),
        "description": "Vendor verification lifecycle.",
    },
    "visibility": {
        "values": ("public", "unlisted"),
        "description": "Listing posture (I-3.5).",
    },
    "source_kind": {
        "values": ("github", "upload"),
        "description": "Origin of the scanned bytes (I-3.5).",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def camel_to_snake(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def pluralize(name: str) -> str:
    """Naive pluralization for table names."""
    if name.endswith("y") and name[-2] not in "aeiou":
        return name[:-1] + "ies"
    if name.endswith(("s", "sh", "ch", "x", "z")):
        return name + "es"
    return name + "s"


def class_name_to_tablename(class_name: str) -> str:
    return pluralize(camel_to_snake(class_name))


def load_schemas(schemas_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all *.schema.json files into memory keyed by filename."""
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(schemas_dir.glob("*.schema.json")):
        with open(path, encoding="utf-8") as f:
            schemas[path.name] = json.load(f)
    return schemas


def resolve_ref(ref: str, schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Resolve a $ref string like 'finding.schema.json#/properties/severity'."""
    if "#" in ref:
        file_part, pointer = ref.split("#", 1)
    else:
        file_part = ref
        pointer = ""

    if "/" in file_part:
        file_part = file_part.rsplit("/", 1)[-1]

    schema = schemas.get(file_part)
    if schema is None:
        msg = f"Cannot resolve $ref: file '{file_part}' not found in loaded schemas"
        raise ValueError(msg)

    if not pointer or pointer == "/":
        return schema

    parts = [p for p in pointer.split("/") if p]
    current: Any = schema
    for part in parts:
        if isinstance(current, dict):
            current = current[part]
        else:
            msg = f"Cannot resolve JSON pointer '{pointer}' in '{file_part}'"
            raise ValueError(msg)
    return current  # type: ignore[no-any-return]


def resolve_property_type(
    prop: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve a property's type information, following $ref and oneOf."""
    if "$ref" in prop:
        resolved = resolve_ref(prop["$ref"], schemas)
        merged = dict(resolved)
        for k, v in prop.items():
            if k.startswith("x-") or k == "description":
                merged[k] = v
        return merged

    if "oneOf" in prop:
        for variant in prop["oneOf"]:
            if "$ref" in variant:
                resolved = resolve_ref(variant["$ref"], schemas)
                merged = dict(resolved)
                for k, v in prop.items():
                    if k.startswith("x-") or k in ("description", "default"):
                        merged[k] = v
                merged["_nullable"] = True
                return merged
            if variant.get("type") == "null":
                continue
        return prop

    return prop


# ---------------------------------------------------------------------------
# Enum collection
# ---------------------------------------------------------------------------
def collect_enums(schemas: dict[str, dict[str, Any]]) -> list[EnumInfo]:
    """Scan all schemas for x-postgresql-enum-type and build EnumInfo list."""
    seen: set[str] = set()
    enums: list[EnumInfo] = []

    def _register(pg_enum: str) -> None:
        if pg_enum in seen:
            return
        seen.add(pg_enum)
        info = KNOWN_ENUMS.get(pg_enum)
        if info is None:
            msg = (
                f"Unknown x-postgresql-enum-type '{pg_enum}'. "
                f"Register it in KNOWN_ENUMS in scripts/generate_sqlalchemy_models.py "
                f"before regenerating."
            )
            raise ValueError(msg)
        enums.append(
            EnumInfo(
                pg_name=pg_enum,
                var_name=f"{pg_enum}_enum",
                values_const=f"{pg_enum.upper()}_VALUES",
                values=tuple(info["values"]),
                description=info["description"],
            )
        )

    for _filename, schema in schemas.items():
        if schema.get("x-postgresql-skip"):
            continue
        for _prop_name, prop in schema.get("properties", {}).items():
            pg_enum = prop.get("x-postgresql-enum-type")
            if pg_enum:
                _register(pg_enum)
            items = prop.get("items") if isinstance(prop.get("items"), dict) else None
            if items and items.get("x-postgresql-enum-type"):
                _register(items["x-postgresql-enum-type"])
        for extra in schema.get("x-postgresql-extra-columns", []):
            if extra.get("enum_type"):
                _register(extra["enum_type"])

    enums.sort(key=lambda e: e.pg_name)
    return enums


# ---------------------------------------------------------------------------
# Column generation
# ---------------------------------------------------------------------------
def _get_json_type(prop: dict[str, Any]) -> tuple[str, bool]:
    raw_type = prop.get("type")
    if isinstance(raw_type, list):
        non_null = [t for t in raw_type if t != "null"]
        return (non_null[0] if non_null else "string", "null" in raw_type)
    if raw_type is None:
        return ("string", False)
    return (raw_type, False)


def _foreign_key_arg(fk: dict[str, Any]) -> str:
    target = f'"{fk["table"]}.{fk["column"]}"'
    ondelete = fk.get("ondelete")
    if ondelete:
        return f'sa.ForeignKey({target}, ondelete="{ondelete}")'
    return f"sa.ForeignKey({target})"


def _build_column(
    prop_name: str,
    prop: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    required_fields: set[str],
    enum_map: dict[str, EnumInfo],
) -> ColumnInfo:
    """Build a ColumnInfo for a single schema property."""
    col_name = camel_to_snake(prop_name)

    resolved = resolve_property_type(prop, schemas)
    explicit_nullable = resolved.get("_nullable", False)

    pg_enum_type = resolved.get("x-postgresql-enum-type")
    json_type, type_nullable = _get_json_type(resolved)

    is_nullable = type_nullable or explicit_nullable or (prop_name not in required_fields)
    # Explicit override wins (the plan's annotations rely on this).
    nullable_override = resolved.get("x-postgresql-nullable")
    if nullable_override is None:
        nullable_override = prop.get("x-postgresql-nullable")
    if nullable_override is not None:
        is_nullable = bool(nullable_override)

    is_array = False
    if isinstance(resolved.get("type"), list):
        non_null = [t for t in resolved["type"] if t != "null"]
        if non_null and non_null[0] == "array":
            is_array = True
            json_type = "array"
    elif resolved.get("type") == "array":
        is_array = True
        json_type = "array"

    column_args: list[str] = []

    if pg_enum_type and pg_enum_type in enum_map:
        enum_info = enum_map[pg_enum_type]
        column_args.append(enum_info.var_name)
        mapped_type = "str | None" if is_nullable else "str"
    elif is_array:
        if resolved.get("x-postgresql-array"):
            items = resolved.get("items", {}) if isinstance(resolved.get("items"), dict) else {}
            item_fmt = items.get("format")
            item_pg_enum = items.get("x-postgresql-enum-type")
            if item_pg_enum and item_pg_enum in enum_map:
                column_args.append(f"sa.ARRAY({enum_map[item_pg_enum].var_name})")
            elif item_fmt == "uuid":
                column_args.append("sa.ARRAY(PgUUID(as_uuid=True))")
            else:
                column_args.append("sa.ARRAY(sa.Text)")
            mapped_type = "list[str] | None" if is_nullable else "list[str]"
        else:
            column_args.append("JSONB")
            mapped_type = "list[Any] | None" if is_nullable else "list[Any]"
    else:
        pg_type_override = resolved.get("x-postgresql-type") or prop.get("x-postgresql-type")
        if isinstance(pg_type_override, str) and pg_type_override.upper() in PG_TYPE_OVERRIDE_MAP:
            sa_type, py_type = PG_TYPE_OVERRIDE_MAP[pg_type_override.upper()]
            column_args.append(sa_type)
            mapped_type = f"{py_type} | None" if is_nullable else py_type
        else:
            fmt = resolved.get("format")
            max_length = resolved.get("maxLength")
            if json_type == "string" and fmt is None and isinstance(max_length, int):
                sa_type = f"sa.String({max_length})"
            else:
                sa_type = TYPE_MAP.get((json_type, fmt)) or TYPE_MAP.get(
                    (json_type, None), "sa.Text"
                )
            column_args.append(sa_type)
            py_type = MAPPED_TYPE_MAP.get((json_type, fmt)) or MAPPED_TYPE_MAP.get(
                (json_type, None), "str"
            )
            mapped_type = f"{py_type} | None" if is_nullable else py_type

    # `metadata` is reserved on DeclarativeBase — map attr `item_metadata`,
    # column name "metadata" (matches the hand-written CatalogItem).
    if col_name == "metadata":
        col_name = "item_metadata"
        column_args.insert(0, '"metadata"')

    fk = resolved.get("x-foreign-key") or prop.get("x-foreign-key")
    if fk:
        column_args.append(_foreign_key_arg(fk))

    is_explicit_pk = resolved.get("x-primary-key") or prop.get("x-primary-key")
    if (col_name == "id" and prop_name in required_fields) or is_explicit_pk:
        column_args.append("primary_key=True")

    column_args.append(f"nullable={is_nullable}")

    if resolved.get("x-postgresql-unique"):
        column_args.append("unique=True")

    pg_default = resolved.get("x-postgresql-default")
    if pg_default:
        column_args.append(f'server_default=sa.text("{pg_default}")')

    pg_on_update = resolved.get("x-postgresql-on-update")
    if pg_on_update:
        column_args.append(f"onupdate=sa.func.{pg_on_update}")

    return ColumnInfo(name=col_name, mapped_type=mapped_type, column_args=column_args)


def _build_extra_column(extra: dict[str, Any], enum_map: dict[str, EnumInfo]) -> ColumnInfo:
    """Build a ColumnInfo from an x-postgresql-extra-columns entry."""
    col_name = extra["name"]
    col_type = str(extra["type"])
    is_nullable = extra.get("nullable", True)

    column_args: list[str] = []

    pg_enum = extra.get("enum_type")
    if pg_enum and pg_enum in enum_map:
        column_args.append(enum_map[pg_enum].var_name)
        mapped_type = "str | None" if is_nullable else "str"
    else:
        length = extra.get("length")
        type_mapping: dict[str, tuple[str, str]] = {
            "uuid": ("PgUUID(as_uuid=True)", "UUID"),
            "timestamp": ("sa.DateTime(timezone=True)", "datetime"),
            "text": ("sa.Text", "str"),
            "integer": ("sa.Integer", "int"),
            "boolean": ("sa.Boolean", "bool"),
            "jsonb": ("JSONB", "dict[str, Any]"),
            "bytea": ("sa.LargeBinary", "bytes"),
        }
        col_type_lower = col_type.lower()
        if col_type_lower in ("varchar", "string") and isinstance(length, int):
            sa_col, py_type = f"sa.String({length})", "str"
        elif col_type_lower in ("varchar", "string"):
            sa_col, py_type = "sa.Text", "str"
        elif col_type_lower == "float":
            sa_col, py_type = f"sa.Float(precision={extra.get('precision', 24)})", "float"
        elif col_type_lower in type_mapping:
            sa_col, py_type = type_mapping[col_type_lower]
        else:
            sa_col, py_type = "sa.Text", "str"
        column_args.append(sa_col)
        mapped_type = f"{py_type} | None" if is_nullable else py_type

    fk = extra.get("foreign_key")
    if fk:
        column_args.append(_foreign_key_arg(fk))

    if extra.get("primary_key"):
        column_args.append("primary_key=True")

    column_args.append(f"nullable={is_nullable}")

    if extra.get("unique"):
        column_args.append("unique=True")

    default = extra.get("default")
    if default:
        column_args.append(f'server_default=sa.text("{default}")')

    on_update = extra.get("on_update")
    if on_update:
        column_args.append(f"onupdate=sa.func.{on_update}")

    return ColumnInfo(name=col_name, mapped_type=mapped_type, column_args=column_args)


# ---------------------------------------------------------------------------
# Index / table_args generation
# ---------------------------------------------------------------------------
def build_table_args(schema: dict[str, Any]) -> list[str]:
    args: list[str] = []

    pk = schema.get("x-postgresql-primary-key") or schema.get("x-postgresql-composite-pk")
    if pk:
        cols = ", ".join(f'"{c}"' for c in pk)
        args.append(f"sa.PrimaryKeyConstraint({cols})")

    for idx in schema.get("x-postgresql-indexes", []):
        cols = ", ".join(f'"{c}"' for c in idx["columns"])
        extra_args: list[str] = []
        if idx.get("unique"):
            extra_args.append("unique=True")
        if idx.get("where"):
            extra_args.append(f'postgresql_where=sa.text("{idx["where"]}")')
        suffix = ", ".join(extra_args)
        if suffix:
            args.append(f'sa.Index("{idx["name"]}", {cols}, {suffix})')
        else:
            args.append(f'sa.Index("{idx["name"]}", {cols})')

    return args


# ---------------------------------------------------------------------------
# Model building
# ---------------------------------------------------------------------------
def build_model(
    schema: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    enum_map: dict[str, EnumInfo],
) -> ModelInfo:
    class_name = schema.get("x-postgresql-classname") or schema.get("title", "")
    tablename = schema.get("x-postgresql-tablename") or class_name_to_tablename(class_name)

    raw_description = schema.get("description", f"{class_name} model.")
    max_desc_len = 106
    if len(raw_description) > max_desc_len:
        description = raw_description[:max_desc_len].rsplit(" ", 1)[0] + "..."
    else:
        description = raw_description

    required_fields = set(schema.get("required", []))
    properties = schema.get("properties", {})
    extra_columns_spec = schema.get("x-postgresql-extra-columns", [])

    columns: list[ColumnInfo] = []
    needs_jsonb = False
    used_enums: set[str] = set()

    for prop_name, prop in properties.items():
        if prop.get("x-postgresql-skip"):
            continue
        resolved = resolve_property_type(prop, schemas)
        col = _build_column(prop_name, prop, schemas, required_fields, enum_map)
        columns.append(col)
        pg_enum = resolved.get("x-postgresql-enum-type")
        if pg_enum and pg_enum in enum_map:
            used_enums.add(pg_enum)
        items = resolved.get("items") if isinstance(resolved.get("items"), dict) else None
        if items and items.get("x-postgresql-enum-type") in enum_map:
            used_enums.add(items["x-postgresql-enum-type"])
        if "JSONB" in col.column_args[0]:
            needs_jsonb = True

    for extra in extra_columns_spec:
        col = _build_extra_column(extra, enum_map)
        columns.append(col)
        if extra.get("enum_type") in enum_map:
            used_enums.add(extra["enum_type"])
        if "JSONB" in col.column_args[0]:
            needs_jsonb = True

    pk = schema.get("x-postgresql-primary-key") or schema.get("x-postgresql-composite-pk")
    if pk:
        for col in columns:
            col.column_args = [a for a in col.column_args if a != "primary_key=True"]

    table_args = build_table_args(schema)

    base_import_parts = [enum_map[pg].var_name for pg in sorted(used_enums)]
    base_imports = ", " + ", ".join(base_import_parts) if base_import_parts else ""

    composite_pk_raw = schema.get("x-postgresql-composite-pk")
    composite_pk_cols = composite_pk_raw if isinstance(composite_pk_raw, list) else None
    repr_fields = _build_repr_fields(class_name, columns, composite_pk_cols)

    needs_datetime = any("datetime" in c.mapped_type for c in columns)
    needs_uuid = any(
        "UUID" in c.mapped_type or "PgUUID" in " ".join(c.column_args) for c in columns
    )

    return ModelInfo(
        class_name=class_name,
        tablename=tablename,
        description=description,
        columns=columns,
        table_args=table_args,
        needs_jsonb=needs_jsonb,
        needs_datetime=needs_datetime,
        needs_uuid=needs_uuid,
        base_imports=base_imports,
        repr_string=repr_fields,
    )


def _build_repr_fields(
    class_name: str, columns: list[ColumnInfo], composite_pk: list[str] | None = None
) -> str:
    has_id = any(c.name == "id" for c in columns)
    if has_id:
        repr_cols = ["id"]
    elif composite_pk:
        repr_cols = list(composite_pk)
    else:
        repr_cols = [columns[0].name] if columns else ["id"]

    if len(repr_cols) == 1:
        for candidate in ("slug", "name", "display_name", "rule_id", "catalog_item_id"):
            if any(c.name == candidate for c in columns):
                repr_cols.append(candidate)
                break

    if len(repr_cols) == 1:
        col = repr_cols[0]
        return f'f"{class_name}({col}={{self.{col}!r}})"'

    fields = ", ".join(f"{c}={{self.{c}!r}}" for c in repr_cols)
    return f'f"{class_name}({fields})"'


# ---------------------------------------------------------------------------
# File output via Jinja2
# ---------------------------------------------------------------------------
def render_base(env: Environment, enums: list[EnumInfo]) -> str:
    return env.get_template("base.py.j2").render(enums=enums)


def render_model(env: Environment, model: ModelInfo) -> str:
    return env.get_template("sqlalchemy_model.py.j2").render(model=model)


def render_init(models: list[ModelInfo], enums: list[EnumInfo]) -> str:
    lines: list[str] = [
        "# DO NOT EDIT — regenerate via: pnpm run generate",
        '"""Generated SQLAlchemy models + shared enum types."""',
        "",
        "from app.models.generated._base import (",
        "    Base,",
    ]
    for enum in enums:
        lines.append(f"    {enum.values_const},")
        lines.append(f"    {enum.var_name},")
    lines.append(")")

    for model in models:
        module_name = camel_to_snake(model.class_name)
        lines.append(f"from app.models.generated.{module_name} import {model.class_name}")

    lines.append("")
    lines.append("__all__ = [")
    lines.append('    "Base",')
    for enum in enums:
        lines.append(f'    "{enum.values_const}",')
        lines.append(f'    "{enum.var_name}",')
    for model in models:
        lines.append(f'    "{model.class_name}",')
    lines.append("]")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    if not SCHEMAS_DIR.is_dir():
        print(f"Error: schemas directory not found at {SCHEMAS_DIR}", file=sys.stderr)
        return 1

    schemas = load_schemas(SCHEMAS_DIR)
    if not schemas:
        print("Error: no *.schema.json files found", file=sys.stderr)
        return 1

    print(f"Loaded {len(schemas)} schema(s) from {SCHEMAS_DIR}")

    enums = collect_enums(schemas)
    enum_map = {e.pg_name: e for e in enums}
    print(f"Found {len(enums)} enum type(s): {[e.pg_name for e in enums]}")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Clear stale outputs so renamed classes (e.g. the old scan_report.py stub →
    # scan.py) don't linger as orphans and drift the committed tree.
    for stale in OUTPUT_DIR.glob("*.py"):
        stale.unlink()

    base_path = OUTPUT_DIR / "_base.py"
    base_path.write_text(render_base(env, enums), encoding="utf-8")
    print(f"  Generated: {base_path.relative_to(SERVICE_ROOT)}")

    models: list[ModelInfo] = []
    for filename, schema in schemas.items():
        if filename in EMBEDDED_SCHEMAS:
            continue
        if schema.get("x-postgresql-skip"):
            print(f"  Skipping {filename}: x-postgresql-skip=true")
            continue
        if not schema.get("x-postgresql-tablename") and not schema.get("title"):
            continue

        model = build_model(schema, schemas, enum_map)
        models.append(model)

        module_name = camel_to_snake(model.class_name)
        model_path = OUTPUT_DIR / f"{module_name}.py"
        model_path.write_text(render_model(env, model), encoding="utf-8")
        print(f"  Generated: {model_path.relative_to(SERVICE_ROOT)}")

    models.sort(key=lambda m: m.class_name)

    init_path = OUTPUT_DIR / "__init__.py"
    init_path.write_text(render_init(models, enums), encoding="utf-8")
    print(f"  Generated: {init_path.relative_to(SERVICE_ROOT)}")

    print("Running ruff format + check on generated files...")
    ruff_files = [str(p) for p in OUTPUT_DIR.glob("*.py")]
    if ruff_files:
        subprocess.run(
            [sys.executable, "-m", "ruff", "format", *ruff_files],
            cwd=str(SERVICE_ROOT),
            check=False,
        )
        subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--fix", *ruff_files],
            cwd=str(SERVICE_ROOT),
            check=False,
        )

    print(f"Done. Generated {len(models)} model(s) + _base.py + __init__.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
