"""Build the teaching examples, and add `id_type` to the older ones.

    python3 tools/make_examples.py

Every example folder ends up holding exactly two files - the source excel and
the configuration excel - so a reader sees only what a real user writes. The
scenarios each one covers are listed in docs/EXAMPLES.md.

Run it from the project root; it overwrites the generated examples 03-05,
07-08, 16-17, and leaves the hand-built 01-02 sources alone, only topping
their configuration up with the `id_type` setting.
"""
import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

TARGET_HEAD = ["setting", "value", "notes"]
SHEET_HEAD = ["table_name", "sheet_name", "layout", "header_row", "data_start_row",
              "data_end_row", "row_filter", "active", "notes"]
COLUMN_HEAD = ["table_name", "source_ref", "source_header", "column_name", "data_type",
               "nullable", "is_key", "column_order", "date_format"]

TARGET_NOTES = {
    "target": "sqlite | postgres",
    "database": "sqlite: file path. postgres: database name",
    "db_schema": "postgres schema, created if absent; blank = public",
    "table_prefix": "prefix put in front of every table name; blank = none",
    "id_type": "integer = database counter keys | uuid = a UUID per row",
}


def write_workbook(path: Path, sheets: dict) -> None:
    """sheets = {sheet name: [row, row, ...]}, first row being the header."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(list(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def config_workbook(path: Path, target: dict, sheets: list, columns: list) -> None:
    rows = [TARGET_HEAD] + [[key, value, TARGET_NOTES[key]] for key, value in target.items()]
    write_workbook(path, {
        "target_config": rows,
        "sheet_config": [SHEET_HEAD] + sheets,
        "column_config": [COLUMN_HEAD] + columns,
    })


# ---------------------------------------------------------------- example 04
def uuid_keys() -> None:
    """Same shape as example 1, with UUID keys instead of counters."""
    folder = EXAMPLES / "03_uuid_keys"
    write_workbook(folder / "orders_source.xlsx", {"Orders": [
        ["Order Id", "Placed On", "Restaurant", "Total"],
        ["ORD-9001", dt.date(2026, 8, 1), "Cafe Nine", 412.50],
        ["ORD-9002", dt.date(2026, 8, 1), "Bharat Retail", 1180.00],
        ["ORD-9003", dt.date(2026, 8, 2), "Acme Foods", 265.75],
        ["ORD-9004", dt.date(2026, 8, 2), "Cafe Nine", 940.20],
    ]})
    config_workbook(
        folder / "orders_config.xlsx",
        {"target": "postgres", "database": "excel_parser", "db_schema": "uuid_keys",
         "table_prefix": None, "id_type": "uuid"},
        [["orders", "Orders", "table", 1, 2, None, None, "Y",
          "id_type = uuid, so orders_id and file_id are UUIDs"]],
        [["orders", "col:A", "Order Id", "order_id_ext", "text", "N", "Y", 1],
         ["orders", "col:B", "Placed On", "placed_on", "date", "Y", "N", 2],
         ["orders", "col:C", "Restaurant", "restaurant", "text", "Y", "N", 3],
         ["orders", "col:D", "Total", "total", "numeric", "Y", "N", 4]])


# ---------------------------------------------------------------- example 05
def prefixed_postgres() -> None:
    """A PostgreSQL destination: named database, schema and table prefix."""
    folder = EXAMPLES / "04_postgres_schema"
    write_workbook(folder / "ledger_source.xlsx", {"Ledger": [
        ["Entry Ref", "Posted On", "Account", "Debit", "Credit"],
        ["JV-1001", dt.date(2026, 8, 1), "4001 Sales", None, 12500.00],
        ["JV-1001", dt.date(2026, 8, 1), "1101 Bank", 12500.00, None],
        ["JV-1002", dt.date(2026, 8, 3), "5001 Commission", 1875.00, None],
        ["JV-1002", dt.date(2026, 8, 3), "1101 Bank", None, 1875.00],
    ]})
    config_workbook(
        folder / "ledger_config.xlsx",
        {"target": "postgres", "database": "excel_parser", "db_schema": "staging",
         "table_prefix": "stg_", "id_type": "integer"},
        [["ledger", "Ledger", "table", 1, 2, None, None, "Y",
          "lands as staging.stg_ledger; credentials come from .env"]],
        [["ledger", "col:A", "Entry Ref", "entry_ref", "text", "N", "Y", 1],
         ["ledger", "col:B", "Posted On", "posted_on", "date", "N", "N", 2],
         ["ledger", "col:C", "Account", "account", "text", "N", "N", 3],
         ["ledger", "col:D", "Debit", "debit", "numeric", "Y", "N", 4],
         ["ledger", "col:E", "Credit", "credit", "numeric", "Y", "N", 5]])


# ---------------------------------------------------------------- example 06
def data_types() -> None:
    """Every data type, and the messy cells each one copes with."""
    folder = EXAMPLES / "05_data_types"
    write_workbook(folder / "types_source.xlsx", {"Types": [
        ["Card", "Amount", "Qty", "Settled On", "Settled At", "Refunded", "Tax %"],
        [" VISA ", "\u20b91,234.50", "42.0", "02-08-2026", "2026-08-02 19:45", "Yes", "18%"],
        ["MASTER", "(\u20b9120.00)", 7, dt.date(2026, 8, 3), dt.datetime(2026, 8, 3, 9, 5),
         "no", "5%"],
        ["RUPAY", "-", "0", "-", "NA", "TRUE", "0%"],
        ["AMEX", 990, 3, "2026/08/05", "not a timestamp", "maybe", "12.5%"],
        [None, 55, 1, dt.date(2026, 8, 6), dt.datetime(2026, 8, 6, 11, 0), "1", "9%"],
    ]})
    config_workbook(
        folder / "types_config.xlsx",
        {"target": "postgres", "database": "excel_parser", "db_schema": "data_types",
         "table_prefix": None, "id_type": "integer"},
        [["card_settlement", "Types", "table", 1, 2, None, None, "Y",
          "one column per data type; row 6 is skipped - card is nullable = N and empty"]],
        [["card_settlement", "col:A", "Card", "card", "text", "N", "Y", 1],
         ["card_settlement", "col:B", "Amount", "amount", "numeric", "Y", "N", 2],
         ["card_settlement", "col:C", "Qty", "qty", "integer", "Y", "N", 3],
         ["card_settlement", "col:D", "Settled On", "settled_on", "date", "Y", "N", 4],
         ["card_settlement", "col:E", "Settled At", "settled_at", "timestamp", "Y", "N", 5],
         ["card_settlement", "col:F", "Refunded", "refunded", "boolean", "Y", "N", 6],
         ["card_settlement", "col:G", "Tax %", "tax_pct", "numeric", "Y", "N", 7]])


# ---------------------------------------------------------------- example 07
def validation_errors() -> None:
    """A configuration written wrongly on purpose - the validator's catalogue."""
    folder = EXAMPLES / "07_validation_errors"
    write_workbook(folder / "broken_source.xlsx", {"Data": [
        ["Ref", "Amount"],
        ["A-1", 100.5],
        ["A-2", 200.0],
    ]})
    config_workbook(
        folder / "broken_config.xlsx",
        # every line here is a mistake the validator names and refuses to load
        {"target": "postgres", "database": "excel_parser", "db_schema": "broken",
         "table_prefix": None, "id_type": "guid"},
        [["good_rows", "Data", "table", 1, 2, None, None, "Y", "the only correct block"],
         ["Bad Name", "Data", "table", 1, 2, None, None, "Y", "table_name with a space"],
         ["bad_rows", "Data", "table", 5, 2, None, None, "Y", "header_row sits inside the data"]],
        [["good_rows", "col:A", "Ref", "ref", "text", "N", "Y", 1],
         ["good_rows", "col:B", "Amount", "amount", "numeric", "Y", "N", 2],
         ["good_rows", "col:B", "Amount", "file_id", "numeric", "Y", "N", 3],
         ["Bad Name", "col:A", "Ref", "ref", "text", "N", "Y", 1],
         ["bad_rows", "column:X", "Ref", "amount; drop", "money", "N", "Y", 1]])


# ---------------------------------------------------------------- example 08
def source_mismatch() -> None:
    """A correct configuration pointed at a workbook that does not match it.

    The source checks only run once the configuration itself is clean, which is
    why these live apart from example 07.
    """
    folder = EXAMPLES / "08_source_mismatch"
    write_workbook(folder / "stock_source.xlsx", {"Stock": [
        ["Sku", "Warehouse", "On Hand", "Counted On"],
        ["SKU-1", "Pune", 12, dt.date(2026, 8, 1)],
        ["SKU-2", None, 4, dt.date(2026, 8, 1)],
        ["SKU-3", "Nashik", "lots", "31-02-2026"],
    ]})
    config_workbook(
        folder / "stock_config.xlsx",
        {"target": "postgres", "database": "excel_parser", "db_schema": "stock",
         "table_prefix": None, "id_type": "integer"},
        [["stock", "Stock", "table", 1, 2, None, None, "Y",
          "col:F is past the used range; row 3 has no warehouse; row 4 has bad cells"],
         ["stock_last_month", "Stock Aug", "table", 1, 2, None, None, "Y",
          "the worksheet does not exist in this month's file"],
         ["stock_empty", "Stock", "table", 1, 90, None, None, "Y",
          "data_start_row is past the end - 0 rows"]],
        [["stock", "col:A", "Sku", "sku", "text", "N", "Y", 1],
         ["stock", "col:B", "Warehouse", "warehouse", "text", "N", "N", 2],
         ["stock", "col:C", "On Hand", "on_hand", "integer", "Y", "N", 3],
         ["stock", "col:D", "Counted On", "counted_on", "date", "Y", "N", 4],
         ["stock", "col:F", "Batch", "batch", "text", "Y", "N", 5],
         ["stock_last_month", "col:A", "Sku", "sku", "text", "N", "Y", 1],
         ["stock_empty", "col:A", "Sku", "sku", "text", "N", "Y", 1]])


# ---------------------------------------------------------------- example 16
def source_ref_showcase() -> None:
    """All four source_ref types, where filter, column name refs, date_format."""
    folder = EXAMPLES / "16_source_ref_showcase"
    # Row 5 has a None discount to demonstrate NULL propagation in expr
    # Row 3 has Gadget B with qty=5 — filtered out by row_filter: col:D >= 10
    write_workbook(folder / "products_source.xlsx", {"Products": [
        ["Product", "Category", "Price", "Qty", "Tax %", "Discount", "Order Date"],
        ["Widget A", "Electronics", 499.99, 10, 18, 50, "01/15/2026"],
        ["Gadget B", "Electronics", 1299.50, 5, 18, None, "02/20/2026"],
        ["Book C", "Stationery", 89.00, 25, 5, 10, "03/05/2026"],
        ["Pen D", "Stationery", 15.50, 100, 5, None, "12/25/2026"],
    ]})
    config_workbook(
        folder / "products_config.xlsx",
        {"target": "postgres", "database": "excel_parser", "db_schema": "showcase",
         "table_prefix": None, "id_type": "integer"},
        # where: only load rows where qty >= 10 (filters out Gadget B)
        [["products", "Products", "table", 1, 2, 5,
          'col:D >= 10', "Y",
          "showcases all source_ref types + where filter + date_format + column name refs"]],
        [# col: — read from Excel
         #                                                                        date_format
         ["products", "col:A", "Product", "product", "text", "N", "Y", 1, None],
         ["products", "col:B", "Category", "category", "text", "Y", "N", 2, None],
         ["products", "col:C", "Price", "price", "numeric", "Y", "N", 3, None],
         ["products", "col:D", "Qty", "qty", "integer", "Y", "N", 4, None],
         ["products", "col:E", "Tax %", "tax_pct", "numeric", "Y", "N", 5, None],
         ["products", "col:F", "Discount", "discount", "numeric", "Y", "N", 6, None],
         # date_format: pin to MM/DD/YYYY (US format, not DD/MM)
         ["products", "col:G", "Order Date", "order_date", "date", "Y", "N", 7, "%m/%d/%Y"],
         # const: — fixed value for every row
         ["products", "const:INR", None, "currency", "text", "Y", "N", 8, None],
         ["products", "const:warehouse-1", None, "warehouse", "text", "Y", "N", 9, None],
         # fn: — computed at load time (all 5 functions)
         ["products", "fn:now", None, "loaded_at", "timestamp", "Y", "N", 10, None],
         ["products", "fn:today", None, "load_date", "date", "Y", "N", 11, None],
         ["products", "fn:uuid", None, "row_id", "text", "Y", "N", 12, None],
         ["products", "fn:file_name", None, "source_file", "text", "Y", "N", 13, None],
         ["products", "fn:sequence", None, "row_num", "integer", "Y", "N", 14, None],
         # expr: with Excel column refs
         ["products", 'expr:{C} * {D}', None, "subtotal", "numeric", "Y", "N", 15, None],
         # expr: with column name refs (references subtotal computed above)
         ["products", 'expr:{subtotal} * {tax_pct} / 100', None, "tax_amount", "numeric", "Y", "N", 16, None],
         # parentheses + column name refs
         ["products", 'expr:{subtotal} + {tax_amount}', None, "total", "numeric", "Y", "N", 17, None],
         # NULL propagation: discount is NULL for some rows -> net is NULL
         ["products", 'expr:{subtotal} - {discount}', None, "net_discount", "numeric", "Y", "N", 18, None],
         # unary minus
         ["products", 'expr:-{discount}', None, "neg_discount", "numeric", "Y", "N", 19, None],
         # string concat
         ["products", 'expr:{A} & " (" & {B} & ")"', None, "label", "text", "Y", "N", 20, None],
         ["products", 'expr:{A} & " - " & const:INR & " " & {C}', None, "price_label", "text", "Y", "N", 21, None],
        ])


# ---------------------------------------------------------------- example 17
def kitchen_sink() -> None:
    """Every parser feature in one file — the comprehensive regression test.

    3 sheets: Orders (table, where-filtered), Items (table, FK to orders),
    Summary (key_value layout). One inactive block.
    Covers: all 6 data types, all source_ref types (col/const/fn/expr/map),
    all 5 fn: functions, expr with column name refs + parentheses + unary
    minus + NULL propagation, where filter, date_format, null_default,
    references (FK), is_key, scripts (text/numeric/date/guard), active=N,
    key_value layout, map: positional labels, table_prefix, db_schema,
    id_type=uuid.
    """
    folder = EXAMPLES / "17_kitchen_sink"
    # --- source workbook: 3 sheets ---
    write_workbook(folder / "sink_source.xlsx", {
        "Orders": [
            # header row (row 1)
            ["Order ID", "Customer", "Order Date", "Status",
             "Subtotal", "Tax %", "Discount", "Paid", "Notes"],
            # data rows (2-7). Row 4 has Status=Cancelled -> filtered by where
            # Row 6 has messy data: ₹ in amount, bracketed negative, NA dates
            ["ORD-001", "  Acme Foods  ", "01/15/2026", "Active",
             1250.50, 18, 50, "Yes", "first order"],
            ["ORD-002", "bharat retail", "02/28/2026", "Active",
             "₹3,400.00", 18, None, "no", "big order"],
            ["ORD-003", "Cafe Nine", "03/10/2026", "Cancelled",
             890, 5, 25, "true", "will be filtered out"],
            ["ORD-004", " delta Corp ", "12/25/2026", "Active",
             "(120.00)", 18, None, "FALSE", "bracketed = negative"],
            ["ORD-005", "echo systems", "06/01/2026", "Active",
             0, 0, 0, "1", "zero order"],
            ["ORD-006", "FOXTROT INC", "NA", "Active",
             2100, 12.5, 100, "maybe", None],
        ],
        "Items": [
            # header on row 1, data rows 2-9
            ["Order ID", "Item", "Qty", "Unit Price", "Item Date"],
            ["ORD-001", "Widget A", 10, 50.50, "15-Jan-2026"],
            ["ORD-001", "Widget B", 5, 100.00, "15-Jan-2026"],
            ["ORD-002", "Gadget X", 20, 170.00, "28-Feb-2026"],
            ["ORD-003", "Book C", 3, 89.00, "10-Mar-2026"],
            ["ORD-004", "Pen D", 8, 15.50, "25-Dec-2026"],
            ["ORD-004", "Eraser E", 12, 5.00, "25-Dec-2026"],
            ["ORD-005", "Clip F", 0, 2.00, "01-Jun-2026"],
            ["ORD-006", "Box G", 7, 300.00, "-"],
        ],
        "Summary": [
            # key-value layout: label in A, value in B
            ["Report Title", "Monthly Sales Summary"],
            ["Generated On", "01/06/2026"],
            ["Currency", "INR"],
            ["Region", "South India"],
            ["Total Orders", 6],
        ],
        "Archive": [
            # This sheet exists but the block is active=N
            ["Old ID", "Old Data"],
            ["X-001", "stale"],
        ],
    })

    # --- config workbook ---
    # Extended COLUMN_HEAD with all fields: table_name, source_ref, source_header,
    # column_name, data_type, nullable, is_key, column_order, date_format,
    # then we add references, null_default, script, description, unit via a
    # wider row format.
    #
    # We build the workbook manually for the wider column_config.
    import openpyxl as _xl
    wb = _xl.Workbook()
    wb.remove(wb.active)

    # target_config
    tc = wb.create_sheet("target_config")
    tc.append(["setting", "value", "notes"])
    for s, v, n in [
        ("target", "postgres", "sqlite | postgres"),
        ("database", "excel_parser", "database name"),
        ("db_schema", "kitchen_sink", "schema, created if absent"),
        ("table_prefix", "ks_", "prefix on every table"),
        ("id_type", "uuid", "uuid keys for cross-source merging"),
    ]:
        tc.append([s, v, n])

    # sheet_config (with where column)
    sc = wb.create_sheet("sheet_config")
    sc.append(["table_name", "sheet_name", "layout", "header_row",
               "data_start_row", "data_end_row", "row_filter", "active",
               "description", "domain", "notes"])
    sc.append(["orders", "Orders", "table", 1, 2, 7,
               'col:D = "Active"', "Y",
               "Customer orders, filtered to Active only", "sales",
               "where filters out Cancelled orders"])
    sc.append(["items", "Items", "table", 1, 2, 9, None, "Y",
               "Line items for each order", "sales",
               "FK to orders via order_id"])
    sc.append(["summary", "Summary", "key_value", None, 1, 5, None, "Y",
               "Report metadata in key-value format", "meta",
               "key_value layout — no header row"])
    sc.append(["archive", "Archive", "table", 1, 2, None, None, "Y",
               None, None, "active=N — completely skipped"])
    # Set archive to inactive (active is now column 8)
    sc.cell(sc.max_row, 8, "N")

    # column_config (comprehensive)
    cc = wb.create_sheet("column_config")
    cc_head = ["table_name", "source_ref", "source_header", "column_name",
               "data_type", "nullable", "is_key", "column_order",
               "date_format", "references", "null_default", "script",
               "description", "unit"]
    cc.append(cc_head)
    cc_rows = [
        # ── orders table ──
        # col: refs, all 6 data types, scripts, null_default, date_format, is_key
        #              src_ref        src_header    col_name       dtype       null key ord  dfmt         refs         null_def  script             desc                       unit
        ["orders",    "col:A",       "Order ID",   "order_id",    "text",     "N", "Y", 1,  None,        None,        None,     "trim|uppercase",  "unique order identifier",  None],
        ["orders",    "col:B",       "Customer",   "customer",    "text",     "N", "N", 2,  None,        None,        None,     "trim|titlecase",  "customer name, cleaned",   None],
        ["orders",    "col:C",       "Order Date", "order_date",  "date",     "Y", "N", 3,  "%m/%d/%Y",  None,        None,     None,              "pinned to MM/DD/YYYY",     None],
        ["orders",    "col:D",       "Status",     "status",      "text",     "N", "N", 4,  None,        None,        None,     "trim|lowercase",  "active/cancelled",         None],
        ["orders",    "col:E",       "Subtotal",   "subtotal",    "numeric",  "Y", "N", 5,  None,        None,        "0",      None,              "handles ₹, commas, (neg)", "INR"],
        ["orders",    "col:F",       "Tax %",      "tax_pct",     "numeric",  "Y", "N", 6,  None,        None,        "0",      None,              "tax percentage",           "percent"],
        ["orders",    "col:G",       "Discount",   "discount",    "numeric",  "Y", "N", 7,  None,        None,        "0",      None,              "NULL -> 0 via null_default", "INR"],
        ["orders",    "col:H",       "Paid",       "is_paid",     "boolean",  "Y", "N", 8,  None,        None,        None,     None,              "yes/no/true/false/1/0",    None],
        ["orders",    "col:I",       "Notes",      "notes",       "text",     "Y", "N", 9,  None,        None,        "N/A",    None,              "null_default = N/A",       None],
        # fn: all 5 functions
        ["orders",    "fn:now",      None,         "loaded_at",   "timestamp","Y", "N", 10, None,        None,        None,     None,              "fn:now — load timestamp",  None],
        ["orders",    "fn:today",    None,         "load_date",   "date",     "Y", "N", 11, None,        None,        None,     None,              "fn:today — load date",     None],
        ["orders",    "fn:uuid",     None,         "row_uuid",    "text",     "Y", "N", 12, None,        None,        None,     None,              "fn:uuid — unique per row", None],
        ["orders",    "fn:file_name",None,         "source_file", "text",     "Y", "N", 13, None,        None,        None,     None,              "fn:file_name",             None],
        ["orders",    "fn:sequence", None,         "row_num",     "integer",  "Y", "N", 14, None,        None,        None,     None,              "fn:sequence — 1,2,3...",   None],
        # const:
        ["orders",    "const:INR",   None,         "currency",    "text",     "Y", "N", 15, None,        None,        None,     None,              "const: fixed value",       None],
        ["orders",    "const:v2",    None,         "api_version", "text",     "Y", "N", 16, None,        None,        None,     None,              "const: another constant",  None],
        # expr: arithmetic, column name refs, parentheses, unary minus, NULL propagation
        ["orders",    "expr:{subtotal} * {tax_pct} / 100", None, "tax_amount", "numeric","Y", "N", 17, None, None, None, "round_2", "column name refs + round_2", "INR"],
        ["orders",    "expr:{subtotal} + {tax_amount}", None, "gross_total", "numeric", "Y", "N", 18, None, None, None, "round_2", "column name refs", "INR"],
        ["orders",    "expr:{gross_total} - {discount}", None, "net_total", "numeric", "Y", "N", 19, None, None, None, None, "NULL propagation if discount NULL (but null_default=0)", "INR"],
        ["orders",    "expr:-{discount}", None, "neg_discount", "numeric", "Y", "N", 20, None, None, None, None, "unary minus", "INR"],
        ["orders",    "expr:({subtotal} + {tax_amount}) * 0.01", None, "surcharge_1pct", "numeric", "Y", "N", 21, None, None, None, "round_2", "parentheses + literal", "INR"],
        ["orders",    'expr:{A} & " — " & {B}', None, "order_label", "text", "Y", "N", 22, None, None, None, None, "string concat with &", None],
        ["orders",    'expr:{A} & " " & fn:today', None, "id_with_date", "text", "Y", "N", 23, None, None, None, None, "mix col + fn in expr", None],
        # date scripts
        ["orders",    "expr:{order_date}",None,      "order_month",  "text",    "Y", "N", 24, None,        None,        None,     "year_month",      "expr refs computed date + year_month", None],

        # ── items table ── (FK to orders)
        ["items",     "col:A",       "Order ID",   "order_id",    "text",     "N", "Y", 1,  None,        "orders.order_id", None, "trim|uppercase", "FK to orders table",      None],
        ["items",     "col:B",       "Item",       "item_name",   "text",     "N", "N", 2,  None,        None,        None,     "trim",            "item description",         None],
        ["items",     "col:C",       "Qty",        "qty",         "integer",  "Y", "N", 3,  None,        None,        "0",      "clamp_0",         "null_default=0, clamped",  None],
        ["items",     "col:D",       "Unit Price", "unit_price",  "numeric",  "N", "N", 4,  None,        None,        None,     None,              "price per unit",           "INR"],
        ["items",     "col:E",       "Item Date",  "item_date",   "date",     "Y", "N", 5,  "%d-%b-%Y",  None,        None,     None,              "DD-Mon-YYYY format",       None],
        # expr with column name refs
        ["items",     "expr:{qty} * {unit_price}", None, "line_total", "numeric", "Y", "N", 6, None, None, None, "round_2", "computed from col names", "INR"],
        ["items",     "fn:sequence", None,         "line_num",    "integer",  "Y", "N", 7,  None,        None,        None,     None,              "sequence per table",        None],
        # const on items
        ["items",     "const:piece", None,         "unit",        "text",     "Y", "N", 8,  None,        None,        None,     None,              "const: unit of measure",    None],

        # ── summary table ── (key_value layout + map: positional labels)
        ["summary",   "map:Title||Date||Currency||Region||Order Count", None, "field_name", "text", "N", "N", 1, None, None, None, None, "map: user-provided labels", None],
        ["summary",   "col:A",       None,         "label",       "text",     "N", "N", 2,  None,        None,        None,     "trim",            "the key/label from source", None],
        ["summary",   "col:B",       None,         "value",       "text",     "Y", "N", 3,  None,        None,        None,     "trim",            "the value, kept as text",   None],
        ["summary",   "fn:now",      None,         "captured_at", "timestamp","Y", "N", 4,  None,        None,        None,     None,              "when this was loaded",       None],

        # ── archive table ── (active=N, won't be created or loaded)
        ["archive",   "col:A",       "Old ID",     "old_id",      "text",     "N", "Y", 1,  None,        None,        None,     None,              "inactive — skipped entirely", None],
        ["archive",   "col:B",       "Old Data",   "old_data",    "text",     "Y", "N", 2,  None,        None,        None,     None,              "inactive — skipped entirely", None],
    ]
    for row in cc_rows:
        cc.append(row)

    folder.mkdir(parents=True, exist_ok=True)
    wb.save(folder / "sink_config.xlsx")


def add_id_type(config: Path) -> bool:
    """Give an older configuration workbook the `id_type` setting."""
    wb = openpyxl.load_workbook(config)
    if "target_config" not in wb.sheetnames:
        return False
    ws = wb["target_config"]
    settings = [str(row[0].value).strip().lower() for row in ws.iter_rows(min_row=2)
                if row[0].value]
    if "id_type" in settings:
        return False
    ws.append(["id_type", "integer", TARGET_NOTES["id_type"]])
    wb.save(config)
    return True


def annotate(config: Path) -> None:
    """Same header hover notes and help sheets as every other workbook."""
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_template.py"),
                    str(config), "--annotate"], check=True, stdout=subprocess.DEVNULL)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    for build in (uuid_keys, prefixed_postgres, data_types, validation_errors,
                  source_mismatch, source_ref_showcase, kitchen_sink):
        build()
    for config in sorted(EXAMPLES.glob("*/*_config.xlsx")):
        touched = add_id_type(config)
        annotate(config)
        print(f"{config.relative_to(ROOT)}"
              f"{' - added id_type' if touched else ''} - annotated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
