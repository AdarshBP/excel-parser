"""Build the teaching examples, and add `id_type` to the older ones.

    python3 tools/make_examples.py

Every example folder ends up holding exactly two files - the source excel and
the configuration excel - so a reader sees only what a real user writes. The
scenarios each one covers are listed in docs/EXAMPLES.md.

Run it from the project root; it overwrites the generated examples 03-05 and
07-08, and leaves the hand-built 01-02 sources alone, only topping their
configuration up with the `id_type` setting.
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
              "data_end_row", "active", "notes"]
COLUMN_HEAD = ["table_name", "source_ref", "source_header", "column_name", "data_type",
               "nullable", "is_key", "transform", "column_order"]

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
        {"target": "sqlite", "database": "orders.db", "db_schema": None,
         "table_prefix": None, "id_type": "uuid"},
        [["orders", "Orders", "table", 1, 2, None, "Y",
          "id_type = uuid, so orders_id and file_id are UUIDs"]],
        [["orders", "col:A", "Order Id", "order_id_ext", "text", "N", "Y", "trim", 1],
         ["orders", "col:B", "Placed On", "placed_on", "date", "Y", "N", "date", 2],
         ["orders", "col:C", "Restaurant", "restaurant", "text", "Y", "N", "trim", 3],
         ["orders", "col:D", "Total", "total", "numeric", "Y", "N", "money", 4]])


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
        [["ledger", "Ledger", "table", 1, 2, None, "Y",
          "lands as staging.stg_ledger; credentials come from .env"]],
        [["ledger", "col:A", "Entry Ref", "entry_ref", "text", "N", "Y", "trim", 1],
         ["ledger", "col:B", "Posted On", "posted_on", "date", "N", "N", "date", 2],
         ["ledger", "col:C", "Account", "account", "text", "N", "N", "trim", 3],
         ["ledger", "col:D", "Debit", "debit", "numeric", "Y", "N", "money", 4],
         ["ledger", "col:E", "Credit", "credit", "numeric", "Y", "N", "money", 5]])


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
        {"target": "sqlite", "database": "types.db", "db_schema": None,
         "table_prefix": None, "id_type": "integer"},
        [["card_settlement", "Types", "table", 1, 2, None, "Y",
          "one column per data type; row 6 is skipped - card is nullable = N and empty"]],
        [["card_settlement", "col:A", "Card", "card", "text", "N", "Y", "trim", 1],
         ["card_settlement", "col:B", "Amount", "amount", "numeric", "Y", "N", "money", 2],
         ["card_settlement", "col:C", "Qty", "qty", "integer", "Y", "N", None, 3],
         ["card_settlement", "col:D", "Settled On", "settled_on", "date", "Y", "N", "date", 4],
         ["card_settlement", "col:E", "Settled At", "settled_at", "timestamp", "Y", "N",
          "date", 5],
         ["card_settlement", "col:F", "Refunded", "refunded", "boolean", "Y", "N", None, 6],
         ["card_settlement", "col:G", "Tax %", "tax_pct", "numeric", "Y", "N", "percent", 7]])


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
        {"target": "sqlite", "database": "broken.db", "db_schema": None,
         "table_prefix": None, "id_type": "guid"},
        [["good_rows", "Data", "table", 1, 2, None, "Y", "the only correct block"],
         ["Bad Name", "Data", "table", 1, 2, None, "Y", "table_name with a space"],
         ["bad_rows", "Data", "table", 5, 2, None, "Y", "header_row sits inside the data"]],
        [["good_rows", "col:A", "Ref", "ref", "text", "N", "Y", "trim", 1],
         ["good_rows", "col:B", "Amount", "amount", "numeric", "Y", "N", "money", 2],
         ["good_rows", "col:B", "Amount", "file_id", "numeric", "Y", "N", None, 3],
         ["Bad Name", "col:A", "Ref", "ref", "text", "N", "Y", "trim", 1],
         ["bad_rows", "column:X", "Ref", "amount; drop", "money", "N", "Y", "trim", 1]])


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
        {"target": "sqlite", "database": "stock.db", "db_schema": None,
         "table_prefix": None, "id_type": "integer"},
        [["stock", "Stock", "table", 1, 2, None, "Y",
          "col:F is past the used range; row 3 has no warehouse; row 4 has bad cells"],
         ["stock_last_month", "Stock Aug", "table", 1, 2, None, "Y",
          "the worksheet does not exist in this month's file"],
         ["stock_empty", "Stock", "table", 1, 90, None, "Y",
          "data_start_row is past the end - 0 rows"]],
        [["stock", "col:A", "Sku", "sku", "text", "N", "Y", "trim", 1],
         ["stock", "col:B", "Warehouse", "warehouse", "text", "N", "N", "trim", 2],
         ["stock", "col:C", "On Hand", "on_hand", "integer", "Y", "N", None, 3],
         ["stock", "col:D", "Counted On", "counted_on", "date", "Y", "N", "date", 4],
         ["stock", "col:F", "Batch", "batch", "text", "Y", "N", "trim", 5],
         ["stock_last_month", "col:A", "Sku", "sku", "text", "N", "Y", "trim", 1],
         ["stock_empty", "col:A", "Sku", "sku", "text", "N", "Y", "trim", 1]])


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
                  source_mismatch):
        build()
    for config in sorted(EXAMPLES.glob("*/*_config.xlsx")):
        touched = add_id_type(config)
        annotate(config)
        print(f"{config.relative_to(ROOT)}"
              f"{' - added id_type' if touched else ''} - annotated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
