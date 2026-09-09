"""One configured row, read and cast. Shared by the executor and the preview.

The web app has to show what the executor *would* insert, so both go through
`build_row()`: the same cell reads, the same casting, the same "all empty" and
"empty required column" decisions. A preview cannot drift from a load.
"""
from collections import namedtuple

from openpyxl.utils import column_index_from_string

import scripts
import validator
from values import cast

# values:   what would be bound to the INSERT, in column_config order
# cells:    (cell_ref, raw value, column_name, cast value) per column, for display/trace
# bad:      (cell_ref, column_name, message) for values that did not fit their data_type
# missing:  non-nullable columns that came out NULL - the row is skipped
# empty:    every column was NULL - the row is not a row at all
RowRead = namedtuple("RowRead", "values cells bad missing empty")


def _apply_default(value, col):
    """If the cast value is None and a null_default is configured, apply it."""
    if value is not None:
        return value
    nd = str(col.get("null_default") or "").strip()
    if not nd or nd.lower() == "null":
        return None
    dtype = str(col.get("data_type") or "text").strip().lower()
    if dtype in ("numeric", "integer"):
        try:
            num = float(nd)
            return int(num) if dtype == "integer" else num
        except ValueError:
            return None
    if dtype == "boolean":
        return nd.lower() in ("1", "true")
    return nd


def build_row(ws, cols, row_num: int) -> RowRead:
    """Read one worksheet row through the column configuration."""
    values, cells, bad = [], [], []
    for col in cols:
        letter = validator.column_letter(col["source_ref"])
        raw = ws.cell(row_num, column_index_from_string(letter)).value
        try:
            value = cast(raw, str(col["data_type"]).strip().lower())
        except ValueError as exc:
            value = None
            bad.append((f"{letter}{row_num}", col["column_name"], str(exc)))
        value = _apply_default(value, col)
        # Apply scripts after casting and defaults
        script_spec = str(col.get("script") or "").strip()
        if script_spec and value is not None:
            try:
                value = scripts.apply(value, script_spec)
            except scripts.ScriptError as exc:
                bad.append((f"{letter}{row_num}", col["column_name"],
                            f"script '{script_spec}': {exc}"))
        values.append(value)
        cells.append((f"{letter}{row_num}", raw, col["column_name"], value))

    empty = all(v is None for v in values)
    missing = [c["column_name"] for c, v in zip(cols, values)
               if v is None and str(c.get("nullable", "Y")).strip().upper() == "N"]
    return RowRead(values, cells, bad, missing, empty)


def row_range(sheet, ws) -> tuple:
    """The configured (start, end) rows for a block, 1-based and inclusive."""
    start = int(sheet["data_start_row"])
    end = int(sheet["data_end_row"]) if sheet.get("data_end_row") else ws.max_row
    return start, end
