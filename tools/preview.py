"""What the configuration would create, and what it would load - without writing.

`model()` describes the tables (the diagram the app draws) and `previews()`
reads the first rows of every block through `rows.build_row()`, the same code
the executor inserts with. Nothing here opens a database.
"""
from pathlib import Path

import openpyxl

import rows as rowmod
import validator

LINEAGE_TYPES = {"file_id": "text", "file_name": "text", "file_sha256": "text",
                 "source_ref": "text", "sheet_name": "text", "source_row_num": "integer"}
DEFAULT_LIMIT = 20

CONTROL_TABLES = (
    ("load_config_audit", "audit of every load: file, config, and table details", (
        ("audit_id", "id", True, None),
        ("file_id", "text", False, None),
        ("file_name", "text", False, None),
        ("file_sha256", "text", False, None),
        ("source_ref", "text", True, None),
        ("config_ref", "text", True, None),
        ("table_name", "text", False, None),
        ("sheet_name", "text", False, None),
        ("header_row", "integer", True, None),
        ("data_start_row", "integer", True, None),
        ("data_end_row", "integer", True, None),
        ("column_count", "integer", True, None),
        ("row_count", "integer", True, None),
        ("loaded_at", "timestamp", False, None),
    )),
)


def _flag(value, default: str = "Y") -> bool:
    return str(value if value is not None else default).strip().upper() == "Y"


def _key_types(id_type: str) -> tuple:
    """(type shown for a table's own key, type shown for file_id)."""
    return ("uuid", "text") if id_type == "uuid" else ("id", "text")


def model(config: Path, prefix: str = None, id_type: str = None) -> list:
    """One entry per active block: the table, its lineage and its columns."""
    sheets, columns = validator.read_config(config)
    resolved = validator.resolve_target(config, prefix=prefix, id_type=id_type)
    own_key, file_key = _key_types(resolved.id_type)
    tables = []
    for sheet in sheets:
        name = str(sheet["table_name"]).strip()
        cols = [{"name": f"{name}_id", "type": own_key, "nullable": False,
                 "is_key": True, "lineage": True, "source": None, "references": None}]
        cols += [{"name": key, "type": "text" if key == "file_id" else value,
                  "nullable": key == "source_ref", "is_key": False,
                  "lineage": True, "source": None, "references": None}
                 for key, value in LINEAGE_TYPES.items()]
        for col in columns.get(sheet["table_name"], []):
            ref_str = str(col.get("references") or "").strip()
            ref = None
            if ref_str and "." in ref_str:
                ref_table, ref_col = ref_str.rsplit(".", 1)
                ref = {"table": ref_table.strip(), "column": ref_col.strip()}
            nd = str(col.get("null_default") or "").strip()
            cols.append({
                "name": str(col["column_name"]).strip(),
                "type": str(col["data_type"]).strip().lower(),
                "nullable": _flag(col.get("nullable")),
                "is_key": _flag(col.get("is_key"), "N"),
                "lineage": False,
                "references": ref,
                "source": str(col["source_ref"]).strip(),
                "source_header": (str(col["source_header"]).strip()
                                  if col.get("source_header") else None),
                "null_default": nd if nd and nd.lower() != "null" else None,
            })
        tables.append({
            "table_name": name,
            "physical_name": f"{resolved.prefix}{name}",
            "sheet_name": str(sheet["sheet_name"]).strip(),
            "layout": str(sheet.get("layout") or "table").strip(),
            "header_row": sheet.get("header_row"),
            "data_start_row": sheet.get("data_start_row"),
            "data_end_row": sheet.get("data_end_row"),
            "notes": str(sheet["notes"]).strip() if sheet.get("notes") else None,
            "control": False,
            "columns": cols,
        })
    return tables


def control(config: Path, prefix: str = None, id_type: str = None) -> list:
    """The control table (load_config_audit), described like the block tables."""
    resolved = validator.resolve_target(config, prefix=prefix, id_type=id_type)
    own_key, file_key = _key_types(resolved.id_type)
    shown = {"id": own_key, "file_id": file_key}
    return [{
        "table_name": name,
        "physical_name": f"{resolved.prefix}{name}",
        "sheet_name": None,
        "layout": "control",
        "header_row": None,
        "data_start_row": None,
        "data_end_row": None,
        "notes": note,
        "control": True,
        "columns": [{"name": column,
                     "type": shown.get("id" if kind == "id" else column, kind),
                     "nullable": nullable,
                     "is_key": kind == "id", "lineage": True, "source": None,
                     "references": ref}
                    for column, kind, nullable, ref in cols],
    } for name, note, cols in CONTROL_TABLES]


def previews(config: Path, source: Path, limit: int = DEFAULT_LIMIT,
             source_name: str = None) -> dict:
    """{table_name: {columns, rows, ...}} - the first `limit` loadable rows.

    Each row carries the cast value and the cell it came from, so the app can
    show `Sales!A12 -> 1250.5`. Rows the executor would skip are reported the
    same way it reports them, not silently dropped.
    """
    sheets, columns = validator.read_config(config)
    import csv_adapter
    wb = csv_adapter.open_source(source, source_name)
    out = {}
    for sheet in sheets:
        name = str(sheet["table_name"]).strip()
        worksheet = str(sheet["sheet_name"]).strip()
        entry = {"sheet_name": worksheet, "columns": [], "rows": [],
                 "skipped": [], "bad_cells": [], "loadable_rows": 0,
                 "range": None, "missing_sheet": worksheet not in wb.sheetnames}
        out[name] = entry
        if entry["missing_sheet"]:
            continue

        ws = wb[worksheet]
        cols = columns.get(sheet["table_name"], [])
        entry["columns"] = [str(c["column_name"]).strip() for c in cols]
        start, end = rowmod.row_range(sheet, ws)
        entry["range"] = [start, end]

        row_ctx = {"file_name": source.name,
                   "_seq_key": f"_preview_{sheet['table_name']}"}
        # Parse where filter
        where_clause = str(sheet.get("row_filter") or "").strip()
        where_conditions = validator.parse_where(where_clause) if where_clause else []
        for row_num in range(start, end + 1):
            # Apply where filter
            if where_conditions:
                from openpyxl.utils import column_index_from_string as _cis
                def _where_reader(ltr, _ws=ws, _row=row_num):
                    return _ws.cell(_row, _cis(ltr)).value
                if not validator.evaluate_where(where_conditions, _where_reader):
                    continue
            read = rowmod.build_row(ws, cols, row_num, row_ctx)
            for ref, column, message in read.bad:
                entry["bad_cells"].append({"cell": f"{worksheet}!{ref}", "column": column,
                                           "message": message})
            if read.empty:
                continue
            if read.missing:
                entry["skipped"].append({"row": row_num, "columns": read.missing})
                continue
            entry["loadable_rows"] += 1
            if len(entry["rows"]) < limit:
                entry["rows"].append({
                    "source_row_num": row_num,
                    "cells": [{"column": column, "cell": f"{worksheet}!{ref}",
                               "raw": None if raw is None else str(raw),
                               "value": None if value is None else str(value)}
                              for ref, raw, column, value in read.cells],
                })
    return out
