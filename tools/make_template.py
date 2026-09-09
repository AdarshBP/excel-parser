"""Write the blank configuration template a new user starts from.

    python make_template.py ../template/config_template.xlsx

The template is a real, loadable configuration: the three sheets the parser
reads (`target_config`, `sheet_config`, `column_config`) with the exact headers,
a hover comment on every header, one filled example row to copy, and help
sheets that spell out each header, its allowed values and an example.
"""
import argparse
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

HEAD_FILL = PatternFill("solid", fgColor="DDEBF7")
HELP_FILL = PatternFill("solid", fgColor="FFF2CC")
BOLD = Font(bold=True)

# header -> (required?, meaning, allowed values, example)
SHEET_HELP = [
    ("table_name", "yes", "Logical table name for this block. The table created is "
                          "<table_prefix><table_name>.",
     "lowercase letters, digits, underscore; unique in the workbook; max 63 chars",
     "sales"),
    ("sheet_name", "yes", "Worksheet tab in the SOURCE workbook that this block sits on.",
     "must match the tab name character for character (Excel truncates long tab names)",
     "Sales"),
    ("layout", "yes", "Shape of the block. Documentation for the reader - both are read "
                      "cell by cell.",
     "table = header row + data rows | key_value = label column + value column",
     "table"),
    ("header_row", "no", "Row that holds the printed headers. Never read as data; kept for "
                         "the audit table.",
     "whole number, 1-based as shown in Excel; blank for key_value", "1"),
    ("data_start_row", "yes", "First row of real data.",
     "whole number, must be below the header/title row", "2"),
    ("data_end_row", "no", "Last row of real data. Set it to fence off a totals row, notes, "
                           "or a second block further down the sheet.",
     "whole number >= data_start_row; blank = read to the last used row", "(blank)"),
    ("active", "yes", "Switch the block off without deleting the rows.",
     "Y = generate the table and load it | N = ignore completely", "Y"),
    ("description", "no", "What this table represents. Written as a PostgreSQL COMMENT ON TABLE "
                          "so AI agents and BI tools can discover the meaning.",
     "any text", "Order-level payout details from the delivery platform"),
    ("domain", "no", "Business domain or category. Written into the table comment as a [tag].",
     "any text, e.g. finance, orders, inventory, hr", "food_delivery"),
    ("notes", "no", "Free text; copied into the generated SQL as a comment.",
     "any text", "invoice lines, one row per invoice"),
]

COLUMN_HELP = [
    ("table_name", "yes", "Which sheet_config block this column belongs to.",
     "must match a table_name on sheet_config", "sales"),
    ("source_ref", "yes", "Which Excel column of that block to read. Read by POSITION - "
                          "re-check it whenever the supplier inserts a column.",
     "col:<letter>, e.g. col:A, col:AM. No row numbers, no ranges, no formulas",
     "col:A"),
    ("source_header", "no", "The header text as printed in the source file.",
     "any text; documentation only, a renamed header does not break the load",
     "Invoice No"),
    ("column_name", "yes", "Database column name to create.",
     "lowercase letters/digits/underscore, unique within the table, max 63 chars; "
     "not file_id, sheet_name, source_row_num or <table_name>_id",
     "invoice_no"),
    ("data_type", "yes", "How the cell is converted. Pick it from the messiest value in the "
                         "column, not the first one.",
     "text | numeric | integer | date | timestamp | boolean", "text"),
    ("nullable", "yes", "May the cell be empty?",
     "Y = allowed | N = NOT NULL, and a row with it empty is rejected and reported",
     "N"),
    ("is_key", "yes", "Create a plain index on this column (for lookups). NOT a primary key "
                      "and it does not deduplicate.",
     "Y | N", "Y"),
    ("transform", "no", "Intent of the cleaning. Documentation - the actual cleaning comes "
                        "from data_type.",
     "trim | money | percent | date | blank", "trim"),
    ("column_order", "yes", "Position of the column in the created table.",
     "whole number; gaps are fine, duplicates make the order arbitrary", "1"),
    ("script", "no", "Predefined transformation(s) applied AFTER type casting. Chain "
                     "multiple with | (e.g. trim|uppercase). Runs during preview, "
                     "validation, and push. Errors block the push.",
     "uppercase | lowercase | titlecase | trim | strip_spaces | digits_only | "
     "letters_only | alphanum_only | abs | round_2 | round_0 | floor | ceil | "
     "negate | date_only | year_month | not_null. Chain: trim|uppercase",
     "trim|uppercase"),
    ("description", "no", "What this column means. Written as a PostgreSQL COMMENT ON COLUMN "
                          "so AI agents and BI tools can discover the meaning.",
     "any text", "Unique order identifier from the platform"),
    ("unit", "no", "Unit of measurement. Appended to the column comment in parentheses.",
     "any text, e.g. INR, USD, percent, count, kg", "INR"),
]

TARGET_HELP = [
    ("target", "no", "Database engine to push into.", "sqlite | postgres (default sqlite)",
     "sqlite"),
    ("database", "no", "SQLite: the file path. PostgreSQL: the database NAME.",
     "any path for sqlite; a plain name for postgres. Blank = take it from the command "
     "line / PGDATABASE", "loaded.db"),
    ("db_schema", "no", "PostgreSQL schema to load into; created if it does not exist.",
     "plain name; blank = public. Ignored by SQLite, which has no schemas", "staging"),
    ("table_prefix", "no", "Put in front of every generated table name, e.g. stg_ turns "
                           "sales into stg_sales.",
     "plain name fragment, letters/digits/underscore; blank = no prefix (default)",
     "(blank)"),
    ("id_type", "no", "How every primary key and the file_id are generated: a database "
                      "counter (1, 2, 3...) or a UUID generated for each row.",
     "integer | uuid (default integer)", "integer"),
]

TYPES = [
    ("text", "trimmed; an empty cell becomes NULL", '" VISA "  ->  VISA'),
    ("numeric", "keeps digits, . and -; a bracketed value becomes negative",
     "\u20b91,234.50 -> 1234.5   18% -> 18.0   (\u20b9120.00) -> -120.0"),
    ("integer", "as numeric, then cut to a whole number", '"42.0"  ->  42'),
    ("date", "Excel dates and common text dates -> YYYY-MM-DD; '-' and 'NA' -> NULL; "
             "anything else -> NULL and reported",
     "02-08-2026  ->  2026-08-02"),
    ("timestamp", "as date, keeping the time", "2026-08-02 19:45  ->  2026-08-02T19:45"),
    ("boolean", "y/yes/true/1 -> 1, n/no/false/0 -> 0, anything else NULL", "Yes  ->  1"),
]

TARGET_NOTE = (
    "One setting per row. Only 'setting' and 'value' are read; 'notes' is yours.\n"
    "Settings: target, database, db_schema, table_prefix, id_type.\n\n"
    "Credentials (host, user, password) are NEVER read from here - they come from "
    "the environment / .env.")

READ_ME = [
    ("Excel Parser - configuration template",),
    (),
    ("This workbook tells the parser what to read and where to push it. Nothing about your",),
    ("source file is hardcoded in the code - it all lives here.",),
    (),
    ("How to use this template",),
    ("1.", "Save a copy named after your source file, e.g. sales_config.xlsx."),
    ("2.", "Fill in target_config: which database, which schema, which table prefix."),
    ("3.", "Fill in sheet_config: ONE ROW PER BLOCK you want loaded (a block = a header row "
           "plus its data rows). Two blocks on one worksheet = two rows here."),
    ("4.", "Fill in column_config: one row per database column you want, pointing at the "
           "Excel column letter it comes from."),
    ("5.", "Delete the example rows (the ones for the 'sales' table) once yours are in."),
    ("6.", "Check it before loading anything:"),
    ("", "python3 tools/validator.py my_config.xlsx my_source.xlsx"),
    ("7.", "When it says 'OK to load', write the schema and push:"),
    ("", "python3 tools/validator.py my_config.xlsx my_source.xlsx --ddl schema.sqlite.sql"),
    ("", "python3 tools/executor.py  my_config.xlsx my_source.xlsx"),
    (),
    ("Rules you cannot get around",),
    ("*", "The three sheet names and the headers on row 1 are read by name - do not rename, "
          "reorder or translate them. Extra columns of your own are ignored."),
    ("*", "NEVER put a host, user, password or connection string in this workbook. Those are "
          "read from the environment / .env only. A workbook gets mailed around; a password "
          "in it is a leak, and the validator refuses one."),
    ("*", "Row numbers are 1-based, exactly as Excel shows them."),
    ("*", "Every table automatically gets <table_name>_id, file_id, sheet_name and "
          "source_row_num, so every row traces back to its worksheet row. Do not add those "
          "yourself."),
    ("*", "Regenerate the schema (--ddl) after ANY change here, before the next load."),
    (),
    ("The help_* sheets explain every header, and each header cell carries the same note as a",),
    ("comment - hover over it. Full rules: docs/CONFIG_RULES.md, running it: docs/RUNNING.md.",),
]


def help_sheet(wb, name: str, title: str, rows) -> None:
    ws = wb.create_sheet(name)
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=12)
    head = ["header / setting", "required", "what it means", "allowed values", "example"]
    ws.append([])
    ws.append(head)
    for cell in ws[3]:
        cell.font = BOLD
        cell.fill = HELP_FILL
    for row in rows:
        ws.append(list(row))
    for col, width in zip("ABCDE", (18, 10, 58, 58, 30)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A4"


def types_sheet(wb) -> None:
    ws = wb.create_sheet("help_data_types")
    ws["A1"] = "data_type - what the loader does to the cell value"
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])
    ws.append(["data_type", "conversion", "example"])
    for cell in ws[3]:
        cell.font = BOLD
        cell.fill = HELP_FILL
    for row in TYPES:
        ws.append(list(row))
    ws.append([])
    ws.append(["A value that does not fit its type is stored as NULL and listed at the end "
               "of the load - fix the data_type when you see that."])
    for col, width in zip("ABC", (14, 70, 52)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def config_sheet(wb, name: str, help_rows, examples) -> None:
    ws = wb.create_sheet(name)
    ws.append([h[0] for h in help_rows])
    for cell, entry in zip(ws[1], help_rows):
        header, required, meaning, allowed, example = entry
        cell.font = BOLD
        cell.fill = HEAD_FILL
        cell.comment = Comment(
            f"{header} ({'required' if required == 'yes' else 'optional'})\n\n"
            f"{meaning}\n\nAllowed: {allowed}\nExample: {example}", "excel parser")
        ws.column_dimensions[cell.column_letter].width = max(14, len(header) + 4)
    for row in examples:
        ws.append(list(row))
    ws.freeze_panes = "A2"


def build(path: Path) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    doc = wb.create_sheet("read_me_first")
    for row in READ_ME:
        doc.append(list(row))
    doc["A1"].font = Font(bold=True, size=14)
    for cell in ("A6", "A20"):
        doc[cell].font = Font(bold=True, size=12)
    doc.column_dimensions["A"].width = 5
    doc.column_dimensions["B"].width = 110
    for row in doc.iter_rows(min_row=7):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    tc = wb.create_sheet("target_config")
    tc.append(["setting", "value", "notes"])
    for cell in tc[1]:
        cell.font = BOLD
        cell.fill = HEAD_FILL
    tc["A1"].comment = Comment(TARGET_NOTE, "excel parser")
    for setting, _req, meaning, allowed, example in TARGET_HELP:
        # db_schema only applies to postgres (a value here while target = sqlite
        # would just earn a warning), and the prefix defaults to none. id_type is
        # spelled out so the choice is visible rather than implied by the default.
        value = "" if setting in ("db_schema", "table_prefix") else example
        tc.append([setting, value, f"{meaning} [{allowed}]"])
    for col, width in zip("ABC", (16, 22, 90)):
        tc.column_dimensions[col].width = width
    for row in tc.iter_rows(min_row=2):
        row[2].alignment = Alignment(vertical="top", wrap_text=True)

    config_sheet(wb, "sheet_config", SHEET_HELP, [
        ["sales", "Sales", "table", 1, 2, None, "Y", "example row - delete me"],
    ])
    config_sheet(wb, "column_config", COLUMN_HELP, [
        ["sales", "col:A", "Invoice No", "invoice_no", "text", "N", "Y", "trim", 1],
        ["sales", "col:B", "Invoice Date", "invoice_date", "date", "Y", "N", "date", 2],
        ["sales", "col:C", "Customer", "customer", "text", "Y", "N", "trim", 3],
        ["sales", "col:D", "Amount", "amount", "numeric", "Y", "N", "money", 4],
    ])

    add_help_sheets(wb)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"wrote {path} ({len(wb.sheetnames)} sheets: {', '.join(wb.sheetnames)})")


def add_help_sheets(wb) -> None:
    """The four reference sheets, replacing any older copy."""
    for name in ("help_target_config", "help_sheet_config", "help_column_config",
                 "help_data_types"):
        if name in wb.sheetnames:
            wb.remove(wb[name])
    help_sheet(wb, "help_target_config", "target_config - where the rows are pushed",
               TARGET_HELP)
    help_sheet(wb, "help_sheet_config", "sheet_config - one row per block to read",
               SHEET_HELP)
    help_sheet(wb, "help_column_config", "column_config - one row per database column",
               COLUMN_HELP)
    types_sheet(wb)


def annotate(path: Path) -> None:
    """Put the template's header comments and help sheets on an existing config.

    Only row 1 and the help sheets are touched, so a hand-written configuration
    keeps every value it had - it just explains itself the way the template does.
    """
    wb = openpyxl.load_workbook(path)
    for name, help_rows in (("sheet_config", SHEET_HELP), ("column_config", COLUMN_HELP)):
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        by_header = {h[0]: h for h in help_rows}
        for cell in ws[1]:
            entry = by_header.get(str(cell.value or "").strip())
            if not entry:
                continue
            header, required, meaning, allowed, example = entry
            cell.font = BOLD
            cell.fill = HEAD_FILL
            cell.comment = Comment(
                f"{header} ({'required' if required == 'yes' else 'optional'})\n\n"
                f"{meaning}\n\nAllowed: {allowed}\nExample: {example}", "excel parser")
            ws.column_dimensions[cell.column_letter].width = max(14, len(header) + 4)
        ws.freeze_panes = "A2"

    if "target_config" in wb.sheetnames:
        ws = wb["target_config"]
        for cell in ws[1]:
            cell.font = BOLD
            cell.fill = HEAD_FILL
        ws["A1"].comment = Comment(TARGET_NOTE, "excel parser")
        by_setting = {s[0]: s for s in TARGET_HELP}
        for row in ws.iter_rows(min_row=2):
            entry = by_setting.get(str(row[0].value or "").strip().lower())
            if entry:
                row[0].comment = Comment(
                    f"{entry[0]} ({'required' if entry[1] == 'yes' else 'optional'})\n\n"
                    f"{entry[2]}\n\nAllowed: {entry[3]}\nExample: {entry[4]}", "excel parser")
        for col, width in zip("ABC", (16, 22, 90)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"

    add_help_sheets(wb)
    wb.save(path)
    print(f"annotated {path} ({', '.join(wb.sheetnames)})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="template/config_template.xlsx")
    ap.add_argument("--annotate", action="store_true",
                    help="add the header comments and help_* sheets to an existing "
                         "configuration workbook instead of writing a new template")
    args = ap.parse_args()
    if args.annotate:
        annotate(Path(args.out))
    else:
        build(Path(args.out))


if __name__ == "__main__":
    main()
