# Configuration Authoring Guide

A step-by-step guide for creating configuration workbooks from scratch.
This document tells you everything you need to build a config that turns
any Excel or CSV source file into structured database tables.

---

## What is a configuration workbook?

It is an `.xlsx` file with **three sheets** that tell the parser:

1. **Where** to push the data (`target_config`)
2. **Which blocks** to read from the source file (`sheet_config`)
3. **Which cells** to read and how to type them (`column_config`)

The parser reads nothing else. No column names are hardcoded in the code —
everything comes from your configuration workbook.

---

## Quick start

```bash
# 1. Copy the template
cp template/config_template.xlsx my_config.xlsx

# 2. Edit it in Excel / Google Sheets (see sections below)

# 3. Validate
python3 tools/validator.py my_config.xlsx my_source.xlsx

# 4. If valid, generate the DDL
python3 tools/validator.py my_config.xlsx my_source.xlsx --ddl schema.postgres.sql

# 5. Push
python3 tools/executor.py my_config.xlsx my_source.xlsx --env .env
```

For CSV source files, you can auto-generate a starting config:

```bash
python3 tools/csv_to_config.py my_data.csv -o my_config.xlsx --table orders --schema my_schema
# Then open my_config.xlsx and refine the types, scripts, descriptions
```

---

## The three sheets

### Sheet 1: `target_config`

Controls **where** the data goes. Two columns: `setting` and `value`.

```
setting        value
target         postgres
database       excel_parser
db_schema      my_schema
table_prefix
id_type        integer
```

| Setting | Required | Default | Description |
|---|---|---|---|
| `target` | no | `sqlite` | Database engine: `postgres` or `sqlite` |
| `database` | no | — | PostgreSQL: database name (e.g., `excel_parser`). SQLite: file path (e.g., `data.db`) |
| `db_schema` | no | `public` | PostgreSQL schema. Created automatically if it doesn't exist. Ignored by SQLite |
| `table_prefix` | no | *(blank)* | Prepended to every table name. E.g., `stg_` turns `sales` into `stg_sales` |
| `id_type` | no | `integer` | `integer` = auto-incrementing keys (1, 2, 3...). `uuid` = UUID per row |

**Rules:**

- **Never put credentials here.** Host, port, user, password go in `.env` only
- The command line (`--target`, `--database`, `--prefix`) overrides these values
- Changing `table_prefix`, `db_schema`, or `id_type` means a new set of tables — regenerate the DDL

---

### Sheet 2: `sheet_config`

One row = one database table. This tells the parser which blocks in the source
file to read.

**Example — simple (one table):**

```
table_name | sheet_name | layout | header_row | data_start_row | data_end_row | active | description     | domain | notes
sales      | Sales      | table  | 1          | 2              |              | Y      | Invoice records | sales  | One row per invoice
```

**Example — complex (multiple tables from one file):**

```
table_name       | sheet_name                      | layout    | header_row | data_start_row | data_end_row | active
summary          | Summary                         | key_value |            | 12             | 20           | Y
payout_breakup   | Payout Breakup                  | table     | 6          | 7              | 43           | Y
order_level      | Order Level                     | table     | 3          | 4              |              | Y
complaint_status | Unresolved Customer Complaints  | table     | 1          | 2              | 16           | Y
```

| Column | Required | Description |
|---|---|---|
| `table_name` | **yes** | Database table name. Lowercase `snake_case`, unique in the workbook, max 63 chars |
| `sheet_name` | **yes** | Exact worksheet tab name in the source file. **Must match character-for-character** (Excel truncates long names) |
| `layout` | **yes** | `table` (header row + data rows) or `key_value` (label column + value column). Documentation for the reader; both are read cell-by-cell |
| `header_row` | no | Row number of the header (1-based). Recorded for audit only — the loader does not read data from it. Leave blank for `key_value` |
| `data_start_row` | **yes** | First row of real data. 1-based, as shown in Excel. Must be below any header/title row |
| `data_end_row` | no | Last row of data. Leave blank to read to the last used row. **Set it** if a totals row, notes, or another block follows |
| `active` | **yes** | `Y` = generate table and load it. `N` = ignore completely (park it without deleting) |
| `description` | no | What this table represents. Written as `COMMENT ON TABLE` in PostgreSQL. AI agents and BI tools read this |
| `domain` | no | Business domain (e.g., `finance`, `sales`, `food_delivery`). Prepended to the table comment as `[domain]` |
| `notes` | no | Free text. Copied into the generated SQL as a comment |

**Key rules:**

1. **One block = one row.** If a worksheet has two separate header blocks (e.g.,
   "Card" starting at row 3 and "Cash" starting at row 9), add **two rows** with
   the same `sheet_name` but different `table_name` and row ranges
2. If the source sheet doesn't exist, that table is silently skipped (no error)
3. Never point two active rows at the same `table_name`
4. When the source file has a **totals row** at the bottom, always set `data_end_row`
   to exclude it — otherwise the totals become a data row

---

### Sheet 3: `column_config`

One row = one database column. This maps source file cells to typed database
columns.

**Example:**

```
table_name | source_ref | source_header | column_name  | data_type | nullable | is_key | column_order | script         | description              | unit
sales      | col:A      | Invoice No    | invoice_no   | text      | N        | Y      | 1            | trim|uppercase | Unique invoice ID        |
sales      | col:B      | Invoice Date  | invoice_date | date      | Y        | N      | 2            |                | Date invoice was issued  |
sales      | col:C      | Customer      | customer     | text      | Y        | N      | 3            | trim|titlecase | Customer name            |
sales      | col:D      | Amount        | amount       | numeric   | Y        | N      | 4            |                | Invoice total            | INR
```

| Column | Required | Description |
|---|---|---|
| `table_name` | **yes** | Must match a `table_name` in `sheet_config` |
| `source_ref` | **yes** | Which Excel column to read. Format: `col:A`, `col:B`, `col:AM`. **Always uppercase letters, no row numbers** |
| `source_header` | no | Header text as printed in the source file. Documentation only — the parser reads by position (`source_ref`), never by header text |
| `column_name` | **yes** | Database column name. Lowercase `snake_case`, unique within the table, max 63 chars. Must not be `file_id`, `file_name`, `file_sha256`, `source_ref`, `sheet_name`, `source_row_num`, or `<table_name>_id` |
| `data_type` | **yes** | One of: `text`, `numeric`, `integer`, `date`, `timestamp`, `boolean` |
| `nullable` | **yes** | `Y` = NULL allowed. `N` = NOT NULL; rows with this cell empty are rejected and reported |
| `is_key` | **yes** | `Y` = create an index on this column (for lookups). Not a primary key, does not deduplicate |
| `transform` | no | Documentation of cleaning intent: `trim`, `money`, `percent`, `date`, blank |
| `column_order` | **yes** | Integer controlling column position in the table. Gaps are fine |
| `references` | no | `table_name.column_name` — declares an FK relationship shown in the ER diagram. Does not create a database constraint |
| `null_default` | no | Value to use when a cell is empty. E.g., `0` for numeric, `N/A` for text. Blank = store NULL |
| `script` | no | Predefined transformation(s). See scripts section below |
| `description` | no | What this column means. Written as `COMMENT ON COLUMN` in PostgreSQL |
| `unit` | no | Unit of measurement (e.g., `INR`, `percent`). Appended to the column comment |

---

## How to determine `source_ref`

Open your source file in Excel. Look at the column letters at the top:

```
    A          B            C          D          E
┌──────────┬────────────┬──────────┬──────────┬──────────┐
│ Order Id │ Order Date │ Customer │ Amount   │ Status   │
├──────────┼────────────┼──────────┼──────────┼──────────┤
│ ORD-001  │ 2026-01-15 │ Acme     │ 1250.50  │ Paid     │
```

- Column A → `col:A`
- Column B → `col:B`
- Column E → `col:E`
- Column AA (the 27th) → `col:AA`

**Important:** If the supplier ever inserts a column in the source file, all
`source_ref` values after that point shift. Always re-check them.

---

## How to determine `data_start_row` and `data_end_row`

```
Row 1:  ┌─── Title: "Monthly Sales Report" ───┐   (skip)
Row 2:  │                                       │  (skip)
Row 3:  │ Invoice No │ Date │ Customer │ Amount │  ← header_row = 3
Row 4:  │ INV-001    │ ...  │ ...      │ ...    │  ← data_start_row = 4
Row 5:  │ INV-002    │ ...  │ ...      │ ...    │
Row 6:  │ INV-003    │ ...  │ ...      │ ...    │  ← data_end_row = 6
Row 7:  │            │      │ TOTAL    │ 3500   │  (totals — exclude!)
```

- `header_row = 3`
- `data_start_row = 4`
- `data_end_row = 6` (set it to exclude the totals row)

If there's no totals row, leave `data_end_row` blank — the parser reads to the
last used row automatically.

---

## Data types in detail

| Type | What the parser does | Example input → output |
|---|---|---|
| `text` | Trims whitespace. Empty → NULL | `" VISA "` → `VISA` |
| `numeric` | Strips currency symbols, commas, `%`. Brackets → negative | `₹1,234.50` → `1234.5`, `(120)` → `-120.0`, `18%` → `18.0` |
| `integer` | Same as numeric, then truncates to whole number | `"42.7"` → `42` |
| `date` | Excel dates and text dates → `YYYY-MM-DD`. `-`/`NA` → NULL | `02-08-2026` → `2026-08-02`, `"Sunday, 07 June 2026"` → `2026-06-07` |
| `timestamp` | Same as date, keeps time | `2026-06-01 17:44:31` → `2026-06-01 17:44:31` |
| `boolean` | `y/yes/true/1` → true; `n/no/false/0` → false; else NULL | `Yes` → `true` |

**Rule of thumb:** Pick the type from the **messiest** value in the column, not
the first one. If any cell has `-`, `NA`, or a text note, use `text`.

A value that doesn't fit its type is stored as **NULL** and reported:
```
order_level: Order Level!AV78 -> cancellation_time stored as NULL,
'75.4' is not a date
```
This is a prompt to fix the `data_type`.

---

## Scripts (cell transformations)

Scripts run **after** type casting, on every cell. Chain multiple with `|`.

```
script: trim|uppercase     →  "  hello world  " becomes "HELLO WORLD"
script: abs|round_2        →  -11.256 becomes 11.26
```

| Script | For | What it does |
|---|---|---|
| `uppercase` | text | → UPPER CASE |
| `lowercase` | text | → lower case |
| `titlecase` | text | → Title Case |
| `trim` | text | Strip leading/trailing whitespace |
| `strip_spaces` | text | Remove ALL whitespace |
| `digits_only` | text | Keep only digits: `INV-2026-001` → `2026001` |
| `letters_only` | text | Keep only letters: `ABC123` → `ABC` |
| `alphanum_only` | text | Keep only letters + digits |
| `abs` | numeric/integer | Absolute value: `-11.25` → `11.25` |
| `round_2` | numeric | Round to 2 decimals |
| `round_0` | numeric | Round to 0 decimals |
| `floor` | numeric/integer | Round down: `10.7` → `10` |
| `ceil` | numeric/integer | Round up: `10.3` → `11` |
| `negate` | numeric/integer | Flip sign: `5` → `-5` |
| `date_only` | timestamp | Strip time: `2026-06-01 17:44` → `2026-06-01` |
| `year_month` | date/timestamp | Extract: `2026-06-15` → `2026-06` |
| `not_null` | any | Error if value is NULL (stricter than `nullable=N`) |

Scripts skip NULL values automatically (except `not_null`).

**Errors from scripts block the push.** If a script fails on any cell, the
row is flagged and the push is refused.

---

## Columns added automatically

Every data table gets these columns for free (do NOT add them to `column_config`):

```sql
<table_name>_id    -- surrogate primary key (integer or UUID)
file_id            -- UUID identifying this load
file_name          -- source file name at load time
file_sha256        -- SHA-256 hash of the source file (for dedup)
source_ref         -- original reference (Drive link, Sheets URL, or local path)
sheet_name         -- worksheet the row came from
source_row_num     -- 1-based Excel row number
```

Plus a unique index on `(file_id, sheet_name, source_row_num)` — so a row can
always be traced back to its exact source.

---

## Metadata for AI agents

Two optional columns make the database self-documenting:

**On `sheet_config`:**
- `description` → becomes `COMMENT ON TABLE sales IS '[sales] Invoice records'`
- `domain` → prepended as a `[tag]` in the comment

**On `column_config`:**
- `description` → becomes `COMMENT ON COLUMN sales.amount IS 'Invoice total (INR)'`
- `unit` → appended in parentheses

An AI agent connecting to the database reads these with:
```sql
SELECT obj_description('sales'::regclass);  -- table description
```

---

## CSV source files

CSV files work identically to Excel. The parser reads them natively (no
conversion). The CSV filename (without `.csv`) becomes the sheet name.

**Auto-generate a starting config:**

```bash
python3 tools/csv_to_config.py monthly_report.csv -o report_config.xlsx \
    --table monthly_report --schema reports --database excel_parser
```

This reads the CSV headers, infers types from the first 100 rows, and writes a
config workbook. Open it and:
1. Fix any types the inference got wrong
2. Add `description` and `unit` for documentation
3. Add `script` for any transformations needed
4. Set `nullable = N` on columns that must always have data

---

## Walkthrough: building a config from scratch

### Step 1: Examine the source file

Open the source file. For each block of data, note:

- **Sheet tab name** (exact spelling)
- **Header row** number
- **First data row** number
- **Last data row** (or is there a totals row?)
- **Column letters** and what they contain

### Step 2: Create `target_config`

```
setting        value
target         postgres
database       excel_parser
db_schema      my_project
id_type        integer
```

### Step 3: Create `sheet_config`

One row per block. Example for a file with two sheets:

```
table_name  | sheet_name       | layout | header_row | data_start_row | data_end_row | active | description
orders      | Order History    | table  | 1          | 2              |              | Y      | Customer orders
payments    | Payment Details  | table  | 3          | 4              | 50           | Y      | Payment records
```

### Step 4: Create `column_config`

For each table, one row per column you want to load:

```
table_name | source_ref | source_header   | column_name    | data_type | nullable | is_key | column_order | script
orders     | col:A      | Order ID        | order_id       | text      | N        | Y      | 1            | trim|uppercase
orders     | col:B      | Order Date      | order_date     | timestamp | Y        | N      | 2            |
orders     | col:C      | Customer Name   | customer_name  | text      | Y        | N      | 3            | trim|titlecase
orders     | col:D      | Amount          | amount         | numeric   | Y        | N      | 4            |
orders     | col:E      | Status          | status         | text      | Y        | N      | 5            | trim|uppercase
```

**Tips:**
- You don't have to include every column. Columns without a row here are ignored
- If two columns have the same header text, give them different `column_name`s
- Start with `nullable = Y` on everything, then set `N` only on columns that are
  truly always populated

### Step 5: Validate

```bash
python3 tools/validator.py my_config.xlsx my_source.xlsx
```

Fix any errors. Common ones:
- `worksheet is missing` → check the `sheet_name` spelling
- `column X is past the last used column` → check `source_ref` letter
- `data_type 'datetime' is not one of (...)` → use `timestamp` not `datetime`
- `unknown script(s): upper` → use `uppercase` not `upper`

### Step 6: Generate DDL and push

```bash
python3 tools/validator.py my_config.xlsx my_source.xlsx --ddl schema.postgres.sql
python3 tools/executor.py my_config.xlsx my_source.xlsx --env .env --trace 2
```

`--trace 2` shows the first 2 rows of each table in detail so you can verify
the mapping is correct.

---

## Common patterns

### Two blocks on one sheet

```
sheet_config:
  card_payments | Payments | table | 3  | 4  | 15 | Y
  cash_payments | Payments | table | 18 | 19 |    | Y
```

Same `sheet_name`, different `table_name` and row ranges.

### Key-value block (summary/header section)

```
sheet_config:
  summary | Summary | key_value | | 12 | 20 | Y

column_config:
  summary | col:A | Label  | label | text | Y | N | 1
  summary | col:B | Value  | value | text | Y | N | 2
```

### Columns with currency symbols

```
column_config:
  orders | col:F | Amount (₹) | amount | numeric | Y | N | 6
```

`numeric` automatically strips `₹`, `$`, commas, and `%`. No script needed.

### Foreign key reference (for ER diagram)

```
column_config:
  items | col:A | Order ID | order_id | text | N | Y | 1 | | | | orders.order_id
```

The `references` column (value: `orders.order_id`) draws a dashed line in the
ER diagram. It does NOT create a database constraint.

---

## Checklist before handover

- [ ] Sheet tab names copied **exactly** from the source workbook
- [ ] `data_start_row` is the first **data** row, not the header
- [ ] `data_end_row` set wherever a totals row or second block follows
- [ ] Every block on a shared sheet has its own `table_name`
- [ ] `column_name` unique per table, `snake_case`, not a reserved name
- [ ] `data_type` chosen from the **messiest** value in the column
- [ ] `nullable = N` only on cells that are always populated
- [ ] `column_order` filled in for every column
- [ ] `source_ref` letters verified against the actual source file
- [ ] `description` and `domain` filled in for AI/BI discoverability
- [ ] Scripts tested (run validator with the source file)
- [ ] Schema regenerated after any config change (`--ddl`)
- [ ] Test load run with `--trace 2` to verify the mapping

---

## What must NEVER go in the configuration workbook

- Database passwords, host names, or connection strings
- The `.env` file handles PostgreSQL credentials (`PGHOST`, `PGUSER`, `PGPASSWORD`)
- The config workbook is safe to share, email, or commit to version control
