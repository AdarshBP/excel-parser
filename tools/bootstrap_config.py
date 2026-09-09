"""Bootstrap an excel parser configuration workbook from a Swiggy payout annexure file.

Reads the source workbook, walks the block definitions below (one block = one
table) and writes a configuration workbook with two driver sheets:

  sheet_config   one row per table  (which sheet / rows to read)
  column_config  one row per column (excel column -> db column + type)

The configuration workbook is the only input to generate_schema.py; edit it by
hand afterwards to rename columns, change types or switch a block off.
"""
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

# table_name, sheet_name, layout, header_row, data_start_row, data_end_row, notes
# One row here = one table. Blocks are read as they are; nothing is derived or
# joined across sheets.
BLOCKS = [
    ("summary", "Summary", "key_value", None, 12, 20,
     "Payout header: label in col B, value in col C"),
    ("payout_breakup", "Payout Breakup", "table", 6, 7, 42,
     "Section/line breakup of the payout"),
    ("order_level", "Order Level", "table", 3, 4, None,
     "One row per order"),
    ("complaint_status", "Unresolved Customer Complaints", "table", 1, 2, 16,
     "Processed / not-processed order counts"),
    ("complaint_orders", "Unresolved Customer Complaints", "table", 21, 22, None,
     "Order level detail of unresolved complaints"),
    ("adjustments_current", "Growth Investments and Other De", "table", 11, 12, 12,
     "Restaurant adjustments, this week block"),
    ("adjustments_previous", "Growth Investments and Other De", "table", 14, 15, 15,
     "Restaurant adjustments, previous weeks block"),
    ("ads_investments_current", "Growth Investments and Other De", "table", 28, 31, 32,
     "Ads investments this week; Invoice Number/Remarks headers sit on row 30"),
    ("ads_investments_previous", "Growth Investments and Other De", "table", 34, 35, 35,
     "Ads investments, previous weeks block"),
    ("recoveries", "Growth Investments and Other De", "table", 46, 47, None,
     "Recovery details"),
    ("discount_summary_swiggy", "Discount Summary", "table", 3, 4, 14,
     "Swiggy discount block"),
    ("discount_summary_toing", "Discount Summary", "table", 17, 18, 20,
     "Toing discount block"),
    ("glossary", "Glossary", "table", 2, 3, None,
     "Field definitions shipped with the annexure"),
]

# extra header cells that live outside the main header row
HEADER_PATCH = {
    ("ads_investments_current", 9): "Invoice Number",
    ("ads_investments_current", 10): "Remarks",
}

# hand corrections applied to the generated names/types: (table prefix, name) -> (name, type)
OVERRIDES = {
    ("payout_breakup", "delivered_orders"): ("swiggy_delivered", "numeric"),
    ("payout_breakup", "cancelled_orders"): ("swiggy_cancelled", "numeric"),
    ("payout_breakup", "delivered_orders_2"): ("toing_delivered", "numeric"),
    ("payout_breakup", "cancelled_orders_2"): ("toing_cancelled", "numeric"),
    ("payout_breakup", "total"): ("total_amount", "numeric"),
    ("order_level", "order_date"): ("order_date", "timestamp"),
    ("order_level", "cancellation_time"): ("cancellation_time", "timestamp"),
    ("order_level", "delivery_fee_sponsored_by_restaurant"): ("delivery_fee_sponsored_by_restaurant", "numeric"),
    ("order_level", "customer_cancellations"): ("customer_cancellations", "numeric"),
    ("order_level", "customer_complaints"): ("customer_complaints", "numeric"),
    ("order_level", "last_mile"): ("last_mile_km", "numeric"),
    ("complaint_status", "payout_period"): ("payout_period", "text"),
    ("complaint_orders", "restaurant_discounts_c1"): ("restaurant_discounts", "numeric"),
    ("complaint_orders", "swiggy_one_exclusive_offer_discount_c2"): ("swiggy_one_exclusive_offer_discount", "numeric"),
    ("complaint_orders", "restaurant_discount_share_c_c1_c2"): ("restaurant_discount_share", "numeric"),
    ("complaint_orders", "net_bill_value_d_a_b_c"): ("net_bill_value", "numeric"),
    ("complaint_orders", "gst_collected_e"): ("gst_collected", "numeric"),
    ("complaint_orders", "total_customer_paid_f_d_e"): ("total_customer_paid", "numeric"),
    ("complaint_orders", "order_date"): ("order_date", "timestamp"),
    ("recoveries", "period_from"): ("period_from", "date"),
    ("discount_summary", "restaurant_share"): ("restaurant_share_pct", "numeric"),
    ("glossary", "s_no"): ("s_no", "numeric"),
}

# columns that are read from a fixed excel column rather than from the header row
DERIVED = {
    "payout_breakup": [("line_ref", "text", "col:B")],
}

TYPE_HINTS = [
    (r"(date|period from|period to|start date|end date|time)$", "date"),
    (r"(order id|parent order id|base order id|invoice number|campaign id|gstin)", "text"),
    (r"(%|share \(%\)|fees %)", "numeric"),
    (r"(total|amount|charges|fees|value|paid|discount|commission|gst|tcs|tds|payout|cashback|refund|km|orders|no of)", "numeric"),
]


def snake(name: str) -> str:
    name = re.sub(r"\[[^\]]*\]", " ", str(name))          # drop [4+5] style formula hints
    name = re.sub(r"\([^)]*\)", " ", name)                 # drop (A), (1) markers
    name = name.replace("%", " pct ").replace("&", " and ")
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    name = re.sub(r"_+", "_", name)
    return name or "col"


def guess_type(header: str) -> str:
    low = str(header).strip().lower()
    for pattern, dtype in TYPE_HINTS:
        if re.search(pattern, low):
            return dtype
    return "text"


def override(table, name, dtype):
    for (tbl, col), value in OVERRIDES.items():
        if table.startswith(tbl) and col == name:
            return value
    return name, dtype


def header_cells(ws, table, header_row):
    out = {}
    for cell in ws[header_row]:
        if cell.value is not None and str(cell.value).strip():
            out[cell.column] = str(cell.value)
    for (tbl, col), value in HEADER_PATCH.items():
        if tbl == table:
            out[col] = value
    return dict(sorted(out.items()))


def main(source: Path, target: Path) -> None:
    wb = openpyxl.load_workbook(source, data_only=True)
    out = openpyxl.Workbook()

    sc = out.active
    sc.title = "sheet_config"
    sc.append(["table_name", "sheet_name", "layout", "header_row", "data_start_row",
               "data_end_row", "active", "notes"])

    cc = out.create_sheet("column_config")
    cc.append(["table_name", "source_ref", "source_header", "column_name", "data_type",
               "nullable", "is_key", "transform", "column_order"])

    tc = out.create_sheet("target_config", 0)
    tc.append(["setting", "value", "notes"])
    for row in [
        ["target", "sqlite", "sqlite | postgres"],
        ["database", "loaded.db", "sqlite: file path. postgres: database name"],
        ["db_schema", "", "postgres schema, created if absent; blank = public"],
        ["table_prefix", "", "prefix put in front of every table name; blank = none"],
    ]:
        tc.append(row)

    for table, sheet, layout, header_row, start, end, notes in BLOCKS:
        if sheet not in wb.sheetnames:
            print(f"skip {table}: sheet {sheet!r} missing", file=sys.stderr)
            continue
        ws = wb[sheet]
        sc.append([table, sheet, layout, header_row, start, end, "Y", notes])

        order = 1
        for name, dtype, ref in DERIVED.get(table, []):
            cc.append([table, ref, "", name, dtype, "Y", "N", "trim", order])
            order += 1

        if layout == "key_value":
            for name, dtype, ref, key in [
                ("field_label", "text", "col:B", "Y"),
                ("field_value", "text", "col:C", "N"),
            ]:
                cc.append([table, ref, "", name, dtype, "N", key, "trim", order])
                order += 1
            continue

        seen, used_source = set(), set()
        for col, header in header_cells(ws, table, header_row).items():
            name = snake(header)
            dtype = guess_type(header)
            suffix = 2
            while (table, name) in used_source:
                name, suffix = f"{snake(header)}_{suffix}", suffix + 1
            used_source.add((table, name))
            name, dtype = override(table, name, dtype)
            base, n = name, 2
            while name in seen:
                name, n = f"{base}_{n}", n + 1
            seen.add(name)
            transform = {"numeric": "money", "date": "date", "timestamp": "date"}.get(dtype, "trim")
            is_key = "Y" if name in ("order_id", "s_no") else "N"
            cc.append([table, f"col:{get_column_letter(col)}", header.strip(), name,
                       dtype, "Y", is_key, transform, order])
            order += 1

    doc = out.create_sheet("readme", 0)
    for row in [
        ["Excel parser configuration"],
        [],
        ["target_config", "where the data goes - never credentials"],
        ["  target", "sqlite | postgres"],
        ["  database", "sqlite file path, or postgres database name"],
        ["  db_schema", "postgres schema name; blank = public"],
        ["  table_prefix", "prefix for every generated table"],
        ["", "host / user / password live in .env only, never in this workbook"],
        [],
        ["sheet_config", "one row per target table"],
        ["  table_name", "physical table name (prefix applied by the generator)"],
        ["  sheet_name", "worksheet to read; several tables may share a sheet"],
        ["  layout", "table = header row + data rows, key_value = label/value pairs"],
        ["  header_row", "1-based row holding the column headers"],
        ["  data_start_row", "1-based first data row"],
        ["  data_end_row", "1-based last data row, blank = read until the sheet ends"],
        ["  active", "Y/N, N skips the table"],
        ["", "one row here = one table; a sheet with two header blocks gets two tables"],
        [],
        ["column_config", "one row per column of a target table"],
        ["  source_ref", "col:<letter> = read that excel column"],
        ["  data_type", "text | numeric | integer | date | timestamp | boolean"],
        ["  transform", "trim | money (strips currency/commas) | date | none"],
        ["  is_key", "Y marks a natural key column (used for the unique index)"],
        [],
        ["Every generated table also carries the lineage columns "
         "file_id, sheet_name and source_row_num."],
    ]:
        doc.append(row)
    doc["A1"].font = Font(bold=True, size=13)

    for ws in (sc, cc, tc, doc):
        for col in range(1, ws.max_column + 1):
            width = max((len(str(ws.cell(r, col).value or "")) for r in range(1, ws.max_row + 1)), default=10)
            ws.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 12), 60)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(vertical="center")
    sc.freeze_panes = cc.freeze_panes = "A2"

    out.save(target)
    print(f"wrote {target} ({sc.max_row - 1} tables, {cc.max_row - 1} columns)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
