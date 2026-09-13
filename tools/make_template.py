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
    ("table_name", "yes",
     "The database table name for this block. The physical table becomes "
     "<table_prefix><table_name>.\n\n"
     "Example: if your source has an 'Orders' tab, you might name it 'orders'. "
     "Two blocks on the same sheet need different names — e.g. 'card_payments' "
     "and 'cash_payments' for two sections on a 'Payments' tab.",
     "lowercase letters, digits, underscore; unique in the workbook; max 63 chars",
     "orders"),
    ("sheet_name", "yes",
     "The exact tab name in the SOURCE workbook. Must match character for "
     "character — copy-paste it from the tab to avoid typos.\n\n"
     "Example: if the tab is called 'Order Level', type exactly 'Order Level'. "
     "Excel truncates long tab names (e.g. 'Growth Investments and Other De'), "
     "so copy the truncated name.",
     "exact tab name from the source file",
     "Order Level"),
    ("layout", "yes",
     "Describes the shape of the data block:\n"
     "  'table' = a header row (e.g. row 1) followed by data rows below it.\n"
     "  'key_value' = labels in one column, values in the next (like a settings block).\n\n"
     "Example: a list of orders with columns Date, Customer, Amount → 'table'. "
     "A summary block with 'Total Orders: 42' on one row → 'key_value'.",
     "table | key_value",
     "table"),
    ("header_row", "no",
     "The row number that contains column headers (e.g. 'Date', 'Customer', "
     "'Amount'). Not read as data — only recorded in the audit log.\n\n"
     "Example: if row 1 has headers and data starts at row 2, set header_row=1. "
     "Leave blank for key_value layout.",
     "whole number, 1-based as shown in Excel; blank for key_value",
     "1"),
    ("data_start_row", "yes",
     "The FIRST row of actual data (not the header, not a title row). "
     "Look at the row numbers in Excel.\n\n"
     "Example: if row 1 is headers and data starts at row 2, set data_start_row=2. "
     "If there is a title on rows 1–3, headers on row 4, and data from row 5, "
     "set data_start_row=5.",
     "whole number, must be below the header/title row",
     "2"),
    ("data_end_row", "no",
     "The LAST row of data. Set this when there are totals, notes, or another "
     "data block below.\n\n"
     "Example: data in rows 2–50, then a 'Grand Total' on row 51 → set "
     "data_end_row=50. If another block starts at row 55, fence this one off "
     "at row 50.\n"
     "Leave blank to read to the last non-empty row in the sheet.",
     "whole number >= data_start_row; blank = read to the last used row",
     "(blank)"),
    ("row_filter", "no",
     "Skip rows that don't match this condition.\n\n"
     "Use col:LETTER to reference a cell (same as source_ref), "
     "then an operator and a value.\n\n"
     "Operators:\n"
     "  =  !=  >  <  >=  <=        compare text or numbers\n"
     "  contains  not_contains     text search inside the cell\n"
     "  is_empty  is_not_empty     check for blank cells (no value needed)\n\n"
     "Examples:\n"
     '  col:A is_not_empty              skip blank rows\n'
     '  col:D > 0                       only positive amounts\n'
     '  col:B = "Delivered"             only delivered orders\n'
     '  col:C != "Cancelled"            exclude cancelled\n'
     '  col:E contains "swiggy"         cell contains the word\n'
     '  col:D > 100 AND col:F != "NA"   combine two conditions\n'
     '  col:A = "Active" OR col:A = "Pending"   either status\n\n'
     "Leave blank to load all rows (default).",
     'col:LETTER op value [AND/OR ...]; blank = all rows',
     ""),
    ("active", "yes",
     "Y = this block is processed (table created, data loaded).\n"
     "N = completely skipped — use this to park a block you do not want "
     "right now without deleting the row.",
     "Y | N",
     "Y"),
    ("description", "no",
     "A human-readable description of what this table contains. "
     "Written as a COMMENT ON TABLE in PostgreSQL so BI tools and AI agents "
     "can discover meaning.\n\n"
     "Example: 'Order-level payout details from the Swiggy annexure'",
     "any text",
     "Order-level payout details from the delivery platform"),
    ("domain", "no",
     "A business category tag. Prepended to the table comment as [domain].\n\n"
     "Example: 'finance', 'orders', 'inventory', 'hr'",
     "any text",
     "food_delivery"),
    ("notes", "no",
     "Free text for your own use. Copied into the generated SQL as a comment.",
     "any text",
     "invoice lines, one row per invoice"),
]

COLUMN_HELP = [
    ("table_name", "yes",
     "Which block (from sheet_config) this column belongs to.\n\n"
     "Example: if you defined a block called 'orders' in sheet_config, "
     "every column row for that block has table_name='orders'.",
     "must match a table_name on sheet_config",
     "orders"),
    ("source_ref", "yes",
     "Where to get the value for this column. Four formats:\n\n"
     "1. Column reference: 'col:<letter>' — reads from the source file by "
     "position, NOT by header text. Example: col:A, col:D, col:AM.\n\n"
     "2. Constant value: 'const:<value>' — fills every row with a fixed "
     "value. Example: const:adarsh, const:100.\n\n"
     "3. Computed value: 'fn:<name>' — fills every row with a value "
     "computed at load time. Available functions:\n"
     "  fn:now       — current timestamp (timestamp, text)\n"
     "  fn:today     — current date (date, text)\n"
     "  fn:uuid      — random UUID per row (text)\n"
     "  fn:file_name — source file name (text)\n"
     "  fn:sequence  — counter 1,2,3... per table (integer, numeric, text)\n\n"
     "4. Expression: 'expr:<expression>' — computes a value from other "
     "columns, constants, functions and literals. Use {X} to reference "
     "Excel column X.\n"
     "  Operators: + - * / (numeric), & (string concatenation)\n"
     "  Grouping: parentheses ( ) to override precedence\n"
     "  Unary minus: -{A} to negate a value\n"
     "  NULL handling: arithmetic with NULL -> NULL (like SQL)\n"
     "  Examples:\n"
     "    expr:{D} + {E}             (sum two columns)\n"
     "    expr:({A} + {B}) * {C}     (grouped arithmetic)\n"
     "    expr:-{D}                  (negate a value)\n"
     "    expr:{A} & \" - \" & {C}    (concatenate with separator)\n"
     "    expr:{D} * 0.18            (calculate 18% tax)\n\n"
     "5. Positional map: 'map:v1||v2||v3||...' — assigns a different "
     "value to each row by position. The first data row gets v1, the "
     "second gets v2, and so on. Use || (double pipe) to separate values.\n"
     "  Example: map:Name||Area||City||ID||GSTIN\n"
     "  Ideal for key_value blocks where the source has no label column.\n"
     "  If the map has fewer values than rows, extra rows get NULL.\n\n"
     "All results are cast to the column's data_type. 'script' and\n"
     "'null_default' apply after the expression result is cast.\n\n"
     "IMPORTANT: if the supplier inserts a new column, every letter after it "
     "shifts. Re-check all col: and expr: source_ref values when that happens.",
     "col:<letter>, const:<value>, fn:<name>, expr:<expression>, or map:v1||v2||...",
     "col:A"),
    ("source_header", "no",
     "The header text as printed in the source file — purely for documentation. "
     "The parser never matches by header text; it always uses source_ref.\n\n"
     "Example: if column A has header 'Invoice No', put 'Invoice No' here. "
     "This shows up in the ER diagram and preview tooltips. If the supplier "
     "renames the header, the load still works — only source_ref matters.",
     "any text; documentation only",
     "Invoice No"),
    ("column_name", "yes",
     "The database column name to create. Must be unique within the table.\n\n"
     "Example: 'Invoice No' → 'invoice_no', 'Order Date' → 'order_date'.\n"
     "Reserved names (added automatically): file_id, sheet_name, "
     "source_row_num, <table_name>_id — do not use these.",
     "lowercase letters/digits/underscore, unique within the table, max 63 chars",
     "invoice_no"),
    ("data_type", "yes",
     "How the cell value is converted. Choose the type based on the MESSIEST "
     "value in the column, not just the first row.\n\n"
     "  text     → keeps the text, trims whitespace. Use for names, IDs, mixed content.\n"
     "  numeric  → extracts numbers: '₹1,234.50' → 1234.5, '18%' → 18.0\n"
     "  integer  → like numeric but truncated: '42.0' → 42\n"
     "  date     → converts to YYYY-MM-DD: '02-Aug-2026' → '2026-08-02'\n"
     "  timestamp → date + time: '2026-08-02 19:45'\n"
     "  boolean  → yes/true/1 → 1, no/false/0 → 0\n\n"
     "If ANY cell can hold '-', 'NA', or a note, use 'text' to avoid NULLs.",
     "text | numeric | integer | date | timestamp | boolean",
     "text"),
    ("nullable", "yes",
     "Can this column be empty in the source?\n\n"
     "  Y = empty cells are stored as NULL (most columns should use this).\n"
     "  N = NOT NULL — any row where this cell is empty is rejected and "
     "reported, not loaded.\n\n"
     "Example: 'order_id' should be N (every order must have an ID). "
     "'discount' should be Y (not all orders have a discount).\n"
     "When in doubt, use Y — it is safer and you can tighten later.",
     "Y | N",
     "Y"),
    ("is_key", "yes",
     "Creates a non-unique INDEX on this column for faster lookups. "
     "This is NOT a primary key and does NOT deduplicate rows.\n\n"
     "Example: set Y on 'order_id' or 'invoice_no' — columns you will "
     "filter or join on. Set N on 'amount', 'description', etc.",
     "Y | N",
     "N"),
    ("column_order", "yes",
     "Controls the position of this column in the created table. "
     "Number them 1, 2, 3... in the order you want.\n\n"
     "Example: invoice_no=1, invoice_date=2, customer=3, amount=4.\n"
     "Gaps are fine (1, 5, 10); duplicates make the order arbitrary.",
     "whole number",
     "1"),
    ("script", "no",
     "Transformations applied AFTER type casting on every cell value. "
     "Chain multiple with | (pipe).\n\n"
     "TEXT examples:\n"
     "  trim             '  hello  ' → 'hello'\n"
     "  uppercase        'hello' → 'HELLO'\n"
     "  lowercase        'HELLO' → 'hello'\n"
     "  titlecase        'hello world' → 'Hello World'\n"
     "  digits_only      'INV-001' → '001'\n"
     "  letters_only     'Order-123' → 'Order'\n"
     "  alphanum_only    'Order #123!' → 'Order123'\n"
     "  collapse_spaces  'hello    world' → 'hello world'\n"
     "  replace_newlines 'line1\\nline2' → 'line1 line2'\n"
     "  remove_punctuation 'Hello, World!' → 'Hello World'\n"
     "  first_word       'John Smith' → 'John'\n"
     "  last_word        'John Smith' → 'Smith'\n"
     "  left_10 / right_10  first/last 10 characters\n"
     "  slug             'Hello World!' → 'hello-world'\n\n"
     "NUMERIC examples:\n"
     "  abs              -120.5 → 120.5\n"
     "  negate           100 → -100\n"
     "  round_2          3.14159 → 3.14\n"
     "  round_1          3.456 → 3.5\n"
     "  round_0          3.7 → 4.0\n"
     "  floor / ceil     3.9 → 3 / 3.1 → 4\n"
     "  pct_to_fraction  18.0 → 0.18\n"
     "  fraction_to_pct  0.18 → 18.0\n"
     "  clamp_0          -5 → 0 (negatives become 0)\n\n"
     "DATE examples:\n"
     "  date_only        '2026-08-02T19:45' → '2026-08-02'\n"
     "  year_month       '2026-08-02' → '2026-08'\n"
     "  year_only        '2026-08-02' → '2026'\n\n"
     "GUARD:\n"
     "  not_null         error if NULL\n"
     "  not_empty        error if NULL or empty string",
     "chain with |, e.g. trim|uppercase",
     "trim"),
    ("description", "no",
     "What this column represents. Written as a COMMENT ON COLUMN in PostgreSQL "
     "so BI tools and AI agents can understand the schema.\n\n"
     "Example: 'Unique order identifier assigned by the platform'",
     "any text",
     "Unique order identifier from the platform"),
    ("unit", "no",
     "Unit of measurement for numeric columns. Appended to the column comment.\n\n"
     "Example: 'INR' for Indian Rupees, 'USD', 'percent', 'count', 'kg'",
     "any text",
     "INR"),
    ("null_default", "no",
     "What to store when a cell is empty, instead of NULL.\n\n"
     "Examples:\n"
     "  numeric/integer column: '0' → stores 0 instead of NULL\n"
     "  text column: 'N/A' or '' → stores that string instead of NULL\n"
     "  boolean column: '0' or 'false' → stores 0 instead of NULL\n\n"
     "Applied after type casting, so a cell with '-' that casts to NULL "
     "also gets the default. Leave blank to keep NULL (the default behavior).",
     "any value appropriate for the data_type; blank = store NULL",
     "0"),
    ("references", "no",
     "Declares a foreign-key relationship to another table's column. "
     "Shown as a dashed line in the ER diagram. Does NOT create a database "
     "constraint — it is for documentation and the diagram only.\n\n"
     "Example: if this column references the 'order_id' column in the "
     "'orders' table, write 'orders.order_id'. The ER diagram will draw "
     "an arrow from this column to orders.order_id.",
     "table_name.column_name (must reference an existing table and column)",
     "orders.order_id"),
    ("date_format", "no",
     "Pin the date parsing to a specific format instead of auto-detecting.\n\n"
     "Without this, the parser tries multiple formats in order — which means "
     "'01/02/2026' could be January 2 or February 1 depending on which "
     "format matches first.\n\n"
     "Set this to eliminate ambiguity:\n"
     "  %d/%m/%Y   → DD/MM/YYYY (European/Indian: 01/02/2026 = Feb 1)\n"
     "  %m/%d/%Y   → MM/DD/YYYY (American: 01/02/2026 = Jan 2)\n"
     "  %Y-%m-%d   → YYYY-MM-DD (ISO)\n"
     "  %d-%b-%Y   → DD-Mon-YYYY (02-Aug-2026)\n\n"
     "Only applies to date and timestamp columns. Ignored for other types.",
     "Python strptime format string; blank = auto-detect",
     ""),
]

TARGET_HELP = [
    ("target", "no",
     "Which database to push into.\n\n"
     "  'sqlite'  → a local file (good for testing and small datasets)\n"
     "  'postgres' → a PostgreSQL server (production use)\n\n"
     "Example: use 'sqlite' while developing, then switch to 'postgres' for production.",
     "sqlite | postgres (default sqlite)",
     "postgres"),
    ("database", "no",
     "SQLite: the file path (e.g. 'loaded.db' creates a file in the working directory).\n"
     "PostgreSQL: the database NAME (e.g. 'excel_parser').\n\n"
     "Leave blank to take it from the command line (--database) or "
     "the PGDATABASE environment variable.",
     "any path for sqlite; a plain name for postgres",
     "excel_parser"),
    ("db_schema", "no",
     "PostgreSQL schema to load into. Created automatically if it does not exist.\n\n"
     "Example: 'staging' puts all tables under the 'staging' schema. "
     "Blank = the 'public' schema. Ignored by SQLite (no schemas).",
     "plain name; blank = public. Ignored by SQLite",
     "staging"),
    ("table_prefix", "no",
     "A prefix added to every table name.\n\n"
     "Example: if table_prefix='stg_' and table_name='orders', "
     "the physical table is 'stg_orders'. Useful for separating staging "
     "from production tables in the same schema.\n"
     "Blank = no prefix (default).",
     "plain name fragment; blank = no prefix",
     "(blank)"),
    ("id_type", "no",
     "How primary keys and file_id are generated.\n\n"
     "  'integer' → auto-incrementing numbers (1, 2, 3...) — simpler, default.\n"
     "  'uuid'    → random UUIDs per row — use when merging data from "
     "multiple sources where integer IDs would collide.",
     "integer | uuid (default integer)",
     "integer"),
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
        ["sales", "Sales", "table", 1, 2, None, None, "Y", None, None, "example row - delete me"],
    ])
    config_sheet(wb, "column_config", COLUMN_HELP, [
        ["sales", "col:A", "Invoice No", "invoice_no", "text", "N", "Y", 1],
        ["sales", "col:B", "Invoice Date", "invoice_date", "date", "Y", "N", 2],
        ["sales", "col:C", "Customer", "customer", "text", "Y", "N", 3],
        ["sales", "col:D", "Amount", "amount", "numeric", "Y", "N", 4],
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
