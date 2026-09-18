# Worked examples of the excel parser

Each example folder holds exactly two files: the **source excel** and the
**configuration excel**. Everything else (schema, database, logs) is produced by
the commands below - see `RUNNING.md` for the general procedure. Regenerate the
generated examples (03-05, 07-08, 16-17) with `python3 tools/make_examples.py`.

| # | folder | read it for |
|---|---|---|
| 1 | `01_simple` | the whole idea: one sheet, one header row, one table |
| 2 | `02_features` | key/value blocks, two blocks on one sheet, fences, rejected rows, `active = N` |
| 3 | `03_uuid_keys` | `id_type = uuid`: UUID primary keys and `file_id` instead of counters |
| 4 | `04_postgres_schema` | a PostgreSQL destination: named database, `db_schema`, `table_prefix`, `.env` credentials |
| 5 | `05_data_types` | every data type and the messy cells each one copes with |
| 6 | `06_references` | cross-table `references` in `column_config`: orders and items linked by `order_id` |
| 7 | `07_validation_errors` | a wrong configuration, and exactly what the validator says about it |
| 8 | `08_source_mismatch` | a right configuration pointed at a workbook that no longer matches it |
| 9 | `09_swiggy_annexure` | a real Swiggy invoice annexure - 14 tables, 222 rows, reconciled against the file itself |
| 10 | `10_zomato_settlement` | a real Zomato settlement report |
| 11 | `11_growthfalcons` | a real GrowthFalcons settlement report - 5 tables, 109 rows |
| 16 | `16_source_ref_showcase` | all four `source_ref` types in one table: `col:`, `const:`, `fn:`, `expr:` |
| 17 | `17_kitchen_sink` | **every parser feature** in one file — the comprehensive regression test |

## Scenario coverage

Every scenario the parser supports, and where to see it:

| Scenario | Example |
|---|---|
| one table from one sheet | 1 |
| several tables from one sheet | 2 (`payments_card`/`payments_cash`), 9 (5 tables from one sheet) |
| block that does not start at row 1 | 2, 9 |
| `key_value` layout (label/value block) | 2 (`report_header`), 9 (`summary`) |
| `data_end_row` fencing off a totals row | 2 (`items`), 9 |
| reading to the last used row (`data_end_row` blank) | 1, 3 |
| block switched off with `active = N` | 2 (`items_archive`) |
| block that legitimately loads 0 rows | 9 (`recoveries`), 8 (`stock_empty`) |
| `text` / `numeric` / `integer` / `date` / `timestamp` / `boolean` | 5 |
| currency, thousands, `%`, bracketed negatives | 5, 2, 9 |
| `-` / `NA` / blank cells becoming NULL | 5 |
| a cell that will not convert - stored NULL and reported | 5 (`E5`), 9 (`Order Level!AV78`), 8 (`D4`) |
| required column empty - row skipped and reported | 2 (`Items!5`), 5 (row 6), 8 (row 3) |
| two Excel columns with the same printed header | 9 (`swiggy_delivered` / `toing_delivered`) |
| integer keys (default) | 1, 2, 4, 5, 9 |
| UUID keys (`id_type = uuid`) | 3 |
| SQLite destination | 1, 2, 3, 5, 6 |
| PostgreSQL destination, schema and table prefix | 4, 9 (`--target postgres`) |
| credentials from `.env` only | 4 |
| lineage: `file_id`, `sheet_name`, `source_row_num`, `source_file` | all |
| `load_config_audit` recording the ranges used | 2, 9 |
| loading a second file into the same tables | 9 ("Next month's file") |
| configuration errors caught before any write | 7 |
| source/configuration mismatch caught before any write | 8 |
| cross-table `references` (FK in the ER diagram) | 6 |
| `map:` positional labels for key-value rows | 17 (`summary.field_name`) |
| real-world settlement reports | 9 (Swiggy), 10 (Zomato), 11 (GrowthFalcons) |

---

# Example 1 - `examples/01_simple`

The whole idea on one page: one sheet, one header row, one table.

## Source excel - `sales_source.xlsx`, sheet `Sales`

|   | A | B | C | D |
|---|---|---|---|---|
| **1** | Invoice No | Invoice Date | Customer | Amount |
| **2** | INV-001 | 2026-08-01 | Acme Foods | 1250.50 |
| **3** | INV-002 | 2026-08-03 | Bharat Retail | 890.00 |
| **4** | INV-003 | 2026-08-04 | Cafe Nine | 2310.75 |

## Configuration excel - `sales_config.xlsx`

`target_config` - where the rows go:

| setting | value |
|---|---|
| target | postgres |
| database | excel_parser |
| db_schema | sales |
| table_prefix | *(blank - tables keep the names in `sheet_config`)* |
| id_type | integer *(counter keys; example 3 uses `uuid`)* |

Host, user and password come from `.env` (copy `.env.example`).

`sheet_config` - one row, so one table:

| table_name | sheet_name | layout | header_row | data_start_row | data_end_row | active |
|---|---|---|---|---|---|---|
| sales | Sales | table | 1 | 2 | *(blank)* | Y |

`data_end_row` blank = read to the end of the sheet.

`column_config` - one row per database column:

| table_name | source_ref | source_header | column_name | data_type | nullable | is_key | column_order |
|---|---|---|---|---|---|---|---|
| sales | col:A | Invoice No | invoice_no | text | N | Y | 1 |
| sales | col:B | Invoice Date | invoice_date | date | Y | N | 2 |
| sales | col:C | Customer | customer | text | Y | N | 3 |
| sales | col:D | Amount | amount | numeric | Y | N | 4 |

## Run

```bash
cd examples/01_simple
python3 ../../tools/validator.py sales_config.xlsx sales_source.xlsx --ddl schema.postgres.sql
python3 ../../tools/executor.py sales_config.xlsx sales_source.xlsx --env ../../.env --trace 3
python3 ../../tools/show_tables.py --config sales_config.xlsx --env ../../.env
```

## What comes out

Schema:

```sql
CREATE TABLE sales (
    sales_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id BIGINT NOT NULL REFERENCES source_file (file_id),
    sheet_name TEXT NOT NULL,
    source_row_num INTEGER NOT NULL,
    invoice_no TEXT NOT NULL,
    invoice_date DATE,
    customer TEXT,
    amount NUMERIC
);
CREATE UNIQUE INDEX ux_sales_row ON sales (file_id, sheet_name, source_row_num);
```

The first four columns are added automatically; the last four come from
`column_config`. `invoice_no` is `NOT NULL` because `nullable = N`, and gets an
index because `is_key = Y`.

How row 2 is pushed (`--trace`):

```
Sales!2 -> sales
  A2      INV-001      -> invoice_no      'INV-001'
  B2      2026-08-01   -> invoice_date    '2026-08-01'
  C2      Acme Foods   -> customer        'Acme Foods'
  D2      1250.5       -> amount          1250.5
  INSERT INTO sales (file_id, sheet_name, source_row_num,
                         invoice_no, invoice_date, customer, amount)
  VALUES (?, ?, ?, ?, ?, ?, ?)
  params: [1, 'Sales', 2, 'INV-001', '2026-08-01', 'Acme Foods', 1250.5]
```

Values travel only as parameters - cell content is never concatenated into SQL.

The table:

```
=== sales  (3 rows) ===
sales_id  file_id  sheet_name  source_row_num  invoice_no  invoice_date  customer       amount
1         1        Sales       2               INV-001     2026-08-01    Acme Foods     1250.5
2         1        Sales       3               INV-002     2026-08-03    Bharat Retail  890
3         1        Sales       4               INV-003     2026-08-04    Cafe Nine      2310.75
```

`source_row_num` is the Excel row: the first data row is worksheet row 2.

## Try this

* Add `Sales Person` in column `E` of the source, add one `column_config` row
  (`col:E`, `sales_person`, `text`, order 5), regenerate, re-load. No code change.
* Set `nullable = N` on `customer` and blank out `C3`: the load prints
  `skip Sales!3: empty required column(s) customer` and loads 2 rows.
* Set `active = N`: the schema comes out with only the two control tables.

---

# Example 2 - `examples/02_features`

Same commands, deliberately awkward workbook: a block that does not start at
row 1, two blocks on one sheet, dirty values, a totals row, a bad row, and a
table switched off.

## Source excel - `report_source.xlsx`

Sheet `Header` - label/value pairs, with a title on row 1 that must not load:

|   | B | C |
|---|---|---|
| **1** | Weekly Store Report | |
| **3** | Report Period | 01 Aug - 07 Aug |
| **4** | Store Code | STR-114 |
| **5** | Currency | INR |
| **6** | Net Payout | ₹12,480.25 |

Sheet `Payments` - two independent blocks on one sheet:

|   | A | B | C |
|---|---|---|---|
| **3** | Card Type | Txn Count | Amount |
| **4** | VISA | 42 | 8110.00 |
| **5** | MASTERCARD | 17 | 2990.25 |
| **6** | AMEX | 3 | 480.00 |
| **9** | Cash Denomination | Notes | Amount |
| **10** | 500 | 2 | 1000.00 |
| **11** | 100 | 9 | 900.00 |

Sheet `Items` - messy on purpose:

|   | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| **1** | Item Code | Item Name | Qty | Gross Amount | Tax % | Sold On |
| **2** | ITM-01 | Paneer Roll | 12 | ₹1,234.50 | 18% | 2026-08-02 |
| **3** | ITM-02 | Veg Biryani | 7 | ₹ 899.00 | 5% | 2026-08-03 |
| **4** | *(completely blank row)* | | | | | |
| **5** | *(no code)* | Mystery item | 1 | ₹50.00 | 5% | 2026-08-03 |
| **6** | ITM-03 | Cold Coffee | 20 | (₹120.00) | 12% | 2026-08-04 |
| **7** | TOTAL | | 39 | ₹2,063.50 | | |

## Configuration excel - `report_config.xlsx`, `sheet_config`

| table_name | sheet_name | layout | header_row | data_start_row | data_end_row | active | why |
|---|---|---|---|---|---|---|---|
| report_header | Header | key_value | | 3 | 6 | Y | block starts at row 3, so the title on row 1 is outside the range |
| payments_card | Payments | table | 3 | 4 | 6 | Y | first block on the sheet |
| payments_cash | Payments | table | 9 | 10 | 11 | Y | second block on the **same** sheet = its own table |
| items | Items | table | 1 | 2 | 6 | Y | stops at row 6, so the TOTAL row 7 never loads |
| items_archive | Items | table | 1 | 2 | 6 | **N** | parked: no table, nothing loaded |

Four features to notice:

1. **`key_value` layout** - `report_header` maps `col:B` to `field_label` and
   `col:C` to `field_value`, so a header block becomes 4 rows of label/value
   instead of 4 columns. A new label next month lands as a new row with no
   configuration change.
2. **Two tables from one sheet** - `payments_card` and `payments_cash` share
   `sheet_name = Payments` and differ only by row range. They stay separate;
   nothing is merged.
3. **`data_end_row` as a fence** - `items` ends at 6 to exclude the totals row;
   `payments_card` ends at 6 so it cannot bleed into the cash block.
4. **`active = N`** - `items_archive` keeps its configuration rows but produces
   nothing.

## Run

```bash
cd examples/02_features
python3 ../../tools/validator.py report_config.xlsx report_source.xlsx --ddl schema.postgres.sql
python3 ../../tools/executor.py report_config.xlsx report_source.xlsx --env ../../.env --trace 2
python3 ../../tools/show_tables.py --config report_config.xlsx --env ../../.env
```

Result: `4 tables + 2 control tables` (the inactive block produced nothing) and
`file_id 1: 12 rows`.

## What comes out

Dirty values cleaned according to `data_type`:

```
Items!2 -> items
  D2      ₹1,234.50   -> gross_amount   1234.5
  E2      18%         -> tax_pct        18.0
  F2      2026-08-02  -> sold_on        '2026-08-02'
```

Row 4 (blank) is skipped silently. Row 5 has no item code and `item_code` is
`nullable = N`, so it is rejected and reported instead of crashing the load:

```
  skip Items!5: empty required column(s) item_code
items                           3 rows from Items!2-6
```

Bracketed amounts read as negative - `(₹120.00)` becomes `-120`:

```
=== items  (3 rows) ===
items_id  file_id  sheet_name  source_row_num  item_code  item_name    qty  gross_amount  tax_pct  sold_on
1         1        Items       2               ITM-01     Paneer Roll  12   1234.5        18       2026-08-02
2         1        Items       3               ITM-02     Veg Biryani  7    899           5        2026-08-03
3         1        Items       6               ITM-03     Cold Coffee  20   -120          12       2026-08-04
```

Note the jump in `source_row_num` (2, 3, 6): the skipped rows stay visible in
the lineage, and row 7 (TOTAL) never came in.

The label/value block, and the two payment blocks kept apart:

```
=== report_header  (4 rows) ===
report_header_id  file_id  sheet_name  source_row_num  field_label    field_value
1                 1        Header      3               Report Period  01 Aug - 07 Aug
2                 1        Header      4               Store Code     STR-114
3                 1        Header      5               Currency       INR
4                 1        Header      6               Net Payout     ₹12,480.25

=== payments_card  (3 rows) ===   VISA / MASTERCARD / AMEX   (Payments!4-6)
=== payments_cash  (2 rows) ===   denominations 500 / 100    (Payments!10-11)
```

`Net Payout` stays text (`₹12,480.25`) because `field_value` is typed `text` -
in a label/value block one column holds mixed kinds of values, so text is the
right call. Convert it when you query it.

The audit trail of the ranges actually used:

```
=== load_config_audit  (4 rows) ===
table_name         sheet_name  header_row  data_start_row  data_end_row  column_count
report_header  Header      None        3               6             2
payments_card  Payments    3           4               6             3
payments_cash  Payments    9           10              11            3
items          Items       1           2               6             6
```

## Try this

* Change `items.data_end_row` from 6 to 7 and re-load: the TOTAL row appears as
  a data row with `item_code = 'TOTAL'`. That is why the fence matters.
* Set `items_archive.active` to `Y` and regenerate: a fifth table appears and
  loads the same rows again into its own table.
* Type `tax_pct` as `text` instead of `numeric`: it stores `18%` verbatim. The
  type decides the cleaning.

---

# Example 3 - `examples/03_uuid_keys`

The same shape as example 1, with one setting changed: `id_type = uuid`.

## Source excel - `orders_source.xlsx`, sheet `Orders`

|   | A | B | C | D |
|---|---|---|---|---|
| **1** | Order Id | Placed On | Restaurant | Total |
| **2** | ORD-9001 | 2026-08-01 | Cafe Nine | 412.5 |
| **3** | ORD-9002 | 2026-08-01 | Bharat Retail | 1180 |
| **4** | ORD-9003 | 2026-08-02 | Acme Foods | 265.75 |
| **5** | ORD-9004 | 2026-08-02 | Cafe Nine | 940.2 |

`data_end_row` is left blank, so the block reads to the last used row - the
validator warns about that, which is the reminder to set a fence if a totals row
ever appears underneath.

## Configuration excel - `orders_config.xlsx`, `target_config`

| setting | value |
|---|---|
| target | postgres |
| database | excel_parser |
| db_schema | uuid_demo |
| id_type | **uuid** |

## Run

```bash
cd examples/03_uuid_keys
python3 ../../tools/validator.py orders_config.xlsx orders_source.xlsx --ddl schema.postgres.sql
python3 ../../tools/executor.py orders_config.xlsx orders_source.xlsx --env ../../.env --trace 1
python3 ../../tools/show_tables.py --config orders_config.xlsx --env ../../.env
```

## What comes out

The DDL header states the mode, and every key column changes type
(`UUID` on PostgreSQL - the loader generates the value, so no
`pgcrypto`/extension is needed):

```sql
-- dialect: postgres, id_type: uuid.
CREATE TABLE orders (
    orders_id UUID PRIMARY KEY,
    file_id UUID NOT NULL REFERENCES source_file (file_id),
    ...
```

```
orders  4 rows from Orders!2-5
file_id b8b05a89-5888-430c-b877-ea3f8ecf224c: 4 rows into postgres excel_parser (schema uuid_demo)
```

```
INSERT INTO orders (orders_id, file_id, sheet_name, source_row_num, ...)
params: ['b7ea4d3a-0424-4e3a-99a6-976ac2f93e2d',
         'b8b05a89-5888-430c-b877-ea3f8ecf224c', 'Orders', 2, 'ORD-9001', ...]
```

Unlike integer mode the id is generated before the insert, so the same row can
be produced in two environments and merged later without collisions.

## Try this

* Set `id_type` back to `integer` and re-run: the same rows come out keyed
  1, 2, 3, 4.
* Do not change `id_type` on a database that already has tables - the column
  types no longer match. Use a fresh database, prefix or schema.
* In the app, the **Keys** selector does the same thing per project and shows
  the mode in the push dialog.

---

# Example 4 - `examples/04_postgres_schema`

Where the data goes, without a single credential in the workbook.

## Source excel - `ledger_source.xlsx`, sheet `Ledger`

|   | A | B | C | D | E |
|---|---|---|---|---|---|
| **1** | Entry Ref | Posted On | Account | Debit | Credit |
| **2** | JV-1001 | 2026-08-01 | 4001 Sales | | 12500 |
| **3** | JV-1001 | 2026-08-01 | 1101 Bank | 12500 | |
| **4** | JV-1002 | 2026-08-03 | 5001 Commission | 1875 | |
| **5** | JV-1002 | 2026-08-03 | 1101 Bank | | 1875 |

Two entries, four lines - `entry_ref` is `is_key = Y` (a lookup index, not a
uniqueness rule), which is exactly right here because the reference repeats.

## Configuration excel - `ledger_config.xlsx`, `target_config`

| setting | value | effect |
|---|---|---|
| target | postgres | psycopg, `%s` placeholders |
| database | excel_parser | `PGDATABASE`, overridden by `--database` |
| db_schema | staging | created if absent; rejected unless it is a plain name |
| table_prefix | stg_ | tables come out `stg_ledger`, `stg_source_file`, `stg_load_config_audit` |
| id_type | integer | counter keys |

Host, user and password are **not** in the workbook. They come from the
environment or a `.env` (`cp ../../.env.example .env`):

```
PGHOST=localhost
PGPORT=5432
PGDATABASE=excel_parser
PGUSER=excel_parser_loader
PGPASSWORD=...          # never committed, never in the workbook
PGSCHEMA=staging        # optional, overrides db_schema
```

## Run

```bash
cd examples/04_postgres_schema
python3 ../../tools/validator.py ledger_config.xlsx ledger_source.xlsx --ddl schema.sql
python3 ../../tools/executor.py ledger_config.xlsx ledger_source.xlsx \
        --schema schema.sql --env .env
python3 ../../tools/show_tables.py --config ledger_config.xlsx --env .env
```

The validator needs no database - it only reads the two workbooks and writes
`schema.sql`. Nothing connects until `executor.py` runs.

## What comes out

```sql
CREATE SCHEMA IF NOT EXISTS staging;
CREATE TABLE staging.stg_ledger (
    ledger_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id BIGINT NOT NULL REFERENCES staging.stg_source_file (file_id),
    ...
    debit NUMERIC(18,4),
    credit NUMERIC(18,4)
);
```

```
file_id 1: 4 rows into postgres excel_parser (schema staging)
```

```
=== stg_ledger  (4 rows) ===
ledger_id  file_id  sheet_name  source_row_num  entry_ref  posted_on   account          debit       credit
1          1        Ledger      2               JV-1001    2026-08-01  4001 Sales                   12500.0000
2          1        Ledger      3               JV-1001    2026-08-01  1101 Bank        12500.0000
```

## Try this

* Run the same pair with `--target sqlite --database ledger.db`: identical rows,
  SQLite types, and `db_schema` reported as ignored.
* Put a quote or semicolon in `db_schema`: rejected before anything is created.
* Change only `table_prefix` and re-run: a second, independent set of tables.

---

# Example 5 - `examples/05_data_types`

One table, one row per card scheme, and every supported `data_type` with the
sort of cell it has to survive.

## Source excel - `types_source.xlsx`, sheet `Types`

|   | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| **1** | Card | Amount | Qty | Settled On | Settled At | Refunded | Tax % |
| **2** | `' VISA '` | ₹1,234.50 | "42.0" | 02-08-2026 | 2026-08-02 19:45 | Yes | 18% |
| **3** | MASTER | (₹120.00) | 7 | *(real date)* | *(real datetime)* | no | 5% |
| **4** | RUPAY | - | 0 | - | NA | TRUE | 0% |
| **5** | AMEX | 990 | 3 | 2026/08/05 | **not a timestamp** | maybe | 12.5% |
| **6** | *(blank)* | 55 | 1 | *(real date)* | *(real datetime)* | 1 | 9% |

`column_config` types them `text`, `numeric`, `integer`, `date`, `timestamp`,
`boolean`, `numeric`, with `card` as `nullable = N`.

## Run

```bash
cd examples/05_data_types
python3 ../../tools/validator.py types_config.xlsx types_source.xlsx --ddl schema.postgres.sql
python3 ../../tools/executor.py types_config.xlsx types_source.xlsx --env ../../.env
python3 ../../tools/show_tables.py --config types_config.xlsx --env ../../.env
```

## What comes out

```
=== card_settlement  (4 rows) ===
card_settlement_id  file_id  sheet_name  source_row_num  card    amount  qty  settled_on  settled_at           refunded  tax_pct
1                   1        Types       2               VISA    1234.5  42   2026-08-02  2026-08-02 19:45:00  1         18
2                   1        Types       3               MASTER  -120    7    2026-08-03  2026-08-03 09:05:00  0         5
3                   1        Types       4               RUPAY           0                                     1         0
4                   1        Types       5               AMEX    990     3    2026-08-05                                 12.5
```

Line by line:

* `' VISA '` -> `VISA`: `text` trims.
* `₹1,234.50` -> `1234.5`, `(₹120.00)` -> `-120`: currency, thousands and
  accounting brackets are stripped; brackets mean negative.
* `18%` -> `18`: the number is kept, the sign dropped - a percentage is stored as
  written, not divided by 100.
* `"42.0"` (text) -> `42`: `integer` truncates.
* `02-08-2026`, `2026/08/05` and real Excel dates all land as `2026-08-02` /
  `2026-08-05`; SQLite stores dates as `TEXT`, PostgreSQL as `DATE`/`TIMESTAMP`.
* `-` and `NA` -> NULL. So do blank cells.
* `Yes`/`no`/`TRUE`/`1` -> true/false; **`maybe` -> NULL, without a warning**,
  because anything unrecognised is neither. Type such a column `text` if you
  need to keep the original word.
* `not a timestamp` cannot be a timestamp, so it is stored as NULL **and
  reported** - by the validator up front and by the executor after the load:

```
warning  types_source.xlsx[Types]!E5: 'not a timestamp' is not a date for
         card_settlement.settled_at (timestamp) - stored as NULL
```

* Row 6 has no `card` and `card` is `nullable = N`, so the row is skipped, not
  the load: `skip Types!6: empty required column(s) card`. That is why 4 rows
  come out of 5 and `source_row_num` runs 2, 3, 4, 5.

## One gotcha worth knowing

A `numeric`/`integer` column keeps only the digits it can find, so `lots` stores
NULL **silently** (no warning) - unlike a bad date, which is reported. If a
column may carry words, type it `text` and convert it in the query.

---

# Example 7 - `examples/07_validation_errors`

A configuration full of mistakes. Nothing here is meant to load - it is here so
you can read the validator's own words for each mistake.

## What is wrong on purpose

| in the workbook | the mistake |
|---|---|
| `target_config[id_type] = guid` | not `integer` or `uuid` |
| `sheet_config[Bad Name]` | a space in `table_name` |
| `column_config[good_rows].file_id` | `file_id` is a reserved lineage column |
| `column_config[bad_rows].amount; drop` | a semicolon and a space in `column_name` |
| `data_type = money` | not a supported type (use `numeric`) |
| `source_ref = column:X` | must be `col:X`, `const:<value>`, `fn:<name>`, or `expr:<expression>` |
| `bad_rows.header_row = 5` with `data_start_row = 2` | the header sits inside the data |
| `good_rows`: `col:B` mapped twice | the same cell is stored in two columns |

## Run

```bash
cd examples/07_validation_errors
python3 ../../tools/validator.py broken_config.xlsx broken_source.xlsx    # exit code 1
python3 ../../tools/executor.py broken_config.xlsx broken_source.xlsx    # refuses to write
```

```
ERROR    target_config[id_type]: 'guid' is not one of ('integer', 'uuid')
ERROR    column_config[good_rows.file_id]: file_id is a reserved lineage column - rename it
ERROR    sheet_config[Bad Name]: table_name must be letters/digits/underscores, start with a letter, and stay under 63 characters including the prefix
ERROR    column_config[bad_rows.amount; drop]: column_name must be letters/digits/underscores, start with a letter, max 63 characters
ERROR    column_config[bad_rows.amount; drop]: data_type 'money' is not one of ('text', 'numeric', 'integer', 'date', 'timestamp', 'boolean')
ERROR    column_config[bad_rows.amount; drop]: 'column:X' is not a 'col:<letter>' reference
warning  column_config[good_rows.file_id]: col:B is already mapped to amount - the cell is stored twice
warning  sheet_config[bad_rows]: header_row 5 is inside the data range - row 2 onwards is read as data

broken_config.xlsx + broken_source.xlsx: NOT loadable - 6 error(s), 5 warning(s)
```

Every problem is listed in one pass - the validator does not stop at the first -
no DDL is written, no database is touched, and the exit code is 1 so a pipeline
can fail on it. Warnings alone would still load; one error is enough to refuse.

## Note on ordering

The source workbook is only dry-run **after** the configuration itself is clean,
so with these six errors present you will not yet see cell-level complaints. Fix
the configuration and the source checks appear - which is what example 8 shows.

---

# Example 8 - `examples/08_source_mismatch`

A correct configuration pointed at a workbook that does not match it: last
month's layout, this month's file. This is the common real failure.

## Source excel - `stock_source.xlsx`, sheet `Stock`

|   | A | B | C | D |
|---|---|---|---|---|
| **1** | Sku | Warehouse | On Hand | Counted On |
| **2** | SKU-1 | Pune | 12 | 2026-08-01 |
| **3** | SKU-2 | *(blank)* | 4 | 2026-08-01 |
| **4** | SKU-3 | Nashik | lots | 31-02-2026 |

## Configuration excel - `stock_config.xlsx`

Three blocks, each disagreeing with the file in a different way: `stock` maps
`col:F` (no such column) and requires `warehouse`; `stock_last_month` reads a
worksheet named `Stock Aug` that this file does not have; `stock_empty` starts
at row 90.

## Run

```bash
cd examples/08_source_mismatch
python3 ../../tools/validator.py stock_config.xlsx stock_source.xlsx     # exit code 1
```

```
ERROR    stock_source.xlsx[Stock]!F: column F is past the last used column - stock.batch would always be empty
ERROR    stock_source.xlsx[Stock Aug]: worksheet is missing - table stock_last_month cannot be loaded (tabs present: Stock)
warning  stock_source.xlsx[Stock]!3: empty required column(s) warehouse - row is skipped
warning  stock_source.xlsx[Stock]!D4: '31-02-2026' is not a date for stock.counted_on (date) - stored as NULL
warning  stock_source.xlsx[Stock]: data_start_row 90 is past the last used row 4 - stock_empty would load 0 rows

stock_config.xlsx + stock_source.xlsx: NOT loadable - 2 error(s), 6 warning(s)
```

Errors versus warnings, and why the split matters:

* **errors** - the configuration cannot be honoured by *this* file (a missing
  worksheet, a column that does not exist). Nothing is loaded.
* **warnings** - the file is loadable, but you should look: a skipped row, a cell
  that will land as NULL, a block that would load nothing.

`31-02-2026` is a date that does not exist, and `lots` in an `integer` column
becomes NULL silently (see the gotcha in example 6).

## Try this

* Delete the `stock_last_month` and `stock.batch` configuration rows and re-run:
  it becomes loadable, and the two warnings about row 3 and `D4` remain.
* This is the check to run in a pipeline before every load - same command, exit
  code 0 or 1.

---

# Example 6 - `examples/06_references`

Cross-table references: two tables (`orders` and `items`) where `items.order_id`
references `orders.order_id`. The `references` column in `column_config` is
purely for documentation and the ER diagram - no database constraint is created.

## Source excel - `refs_source.xlsx`

Sheet `Orders`:

|   | A | B | C | D |
|---|---|---|---|---|
| **1** | Order ID | Order Date | Customer | Total |
| **2** | ORD-001 | 2026-08-01 | Acme Foods | 3500.00 |
| **3** | ORD-002 | 2026-08-02 | Bharat Retail | 1200.50 |
| **4** | ORD-003 | 2026-08-03 | Cafe Nine | 4800.75 |

Sheet `Items`:

|   | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| **1** | Order ID | Item Code | Item Name | Qty | Unit Price | Amount |
| **2** | ORD-001 | ITM-A | Paneer Roll | 10 | 150 | 1500 |
| **3** | ORD-001 | ITM-B | Cold Coffee | 20 | 100 | 2000 |
| **4** | ORD-002 | ITM-A | Paneer Roll | 5 | 150 | 750 |
| **5** | ORD-002 | ITM-C | Veg Biryani | 3 | 150 | 450.50 |
| **6** | ORD-003 | ITM-B | Cold Coffee | 15 | 100 | 1500 |
| **7** | ORD-003 | ITM-D | Masala Dosa | 22 | 150 | 3300.75 |

## Configuration excel - `refs_config.xlsx`

`column_config` for `items` has the key line:

| table_name | column_name | references |
|---|---|---|
| items | order_id | **orders.order_id** |

All other `references` cells are blank - the column is optional.

## Run

```bash
cd examples/06_references
python3 ../../tools/validator.py refs_config.xlsx refs_source.xlsx --ddl schema.postgres.sql
python3 ../../tools/executor.py refs_config.xlsx refs_source.xlsx --env ../../.env --trace 2
python3 ../../tools/show_tables.py --config refs_config.xlsx --env ../../.env
```

Result: 3 orders + 6 items = 9 rows.

## What comes out

```
=== orders  (3 rows) ===
orders_id  file_id  sheet_name  source_row_num  order_id  order_date  customer       total
1          1        Orders      2               ORD-001   2026-08-01  Acme Foods     3500
2          1        Orders      3               ORD-002   2026-08-02  Bharat Retail  1200.5
3          1        Orders      4               ORD-003   2026-08-03  Cafe Nine      4800.75

=== items  (6 rows) ===
items_id  file_id  sheet_name  source_row_num  order_id  item_code  item_name    qty  unit_price  amount
1         1        Items       2               ORD-001   ITM-A      Paneer Roll  10   150         1500
2         1        Items       3               ORD-001   ITM-B      Cold Coffee  20   100         2000
...
```

## In the app

When this example is rendered, the ER diagram shows a **dashed amber line** from
`items.order_id` to `orders.order_id` alongside the usual solid lineage lines
to `source_file`. Clicking either table highlights its connected edges.

---

# Example 9 - `examples/09_swiggy_annexure`

The real invoice annexure. Nothing in the tools is Swiggy-specific; the whole
difference is the configuration workbook.

## Source excel - `swiggy_annexure_4780.xlsx`

7 worksheets: `Summary`, `Payout Breakup`, `Order Level`,
`Unresolved Customer Complaints`, `Growth Investments and Other De`,
`Discount Summary`, `Glossary`. Several hold more than one block, so
`annexure_config.xlsx` declares **13 tables** - the pattern of example 2, at
scale:

| table | sheet | rows read | note |
|---|---|---|---|
| summary | Summary | 12-20 | label/value block (`key_value`) |
| payout_breakup | Payout Breakup | 7-42 | the fee/charge lines |
| order_level | Order Level | 4-end | one row per order, 51 columns |
| complaint_status | Unresolved Customer Complaints | 2-16 | first block |
| complaint_orders | Unresolved Customer Complaints | 22-end | second block, same sheet |
| adjustments_current | Growth Investments and Other De | 12 | this-week block |
| adjustments_previous | Growth Investments and Other De | 15 | previous-weeks block |
| ads_investments_current | Growth Investments and Other De | 31-32 | headers split over rows 28 and 30 |
| ads_investments_previous | Growth Investments and Other De | 35 | |
| recoveries | Growth Investments and Other De | 47-end | |
| discount_summary_swiggy | Discount Summary | 4-14 | Swiggy block |
| discount_summary_toing | Discount Summary | 18-20 | Toing block, same sheet |
| glossary | Glossary | 3-end | definitions shipped with the file |

Five separate tables come out of the single `Growth Investments and Other De`
sheet. They stay apart deliberately - each block is read as it is.

## Run

```bash
cd examples/09_swiggy_annexure
python3 ../../tools/validator.py annexure_config.xlsx swiggy_annexure_4780.xlsx \
        --ddl schema.postgres.sql
python3 ../../tools/executor.py annexure_config.xlsx swiggy_annexure_4780.xlsx \
        --env ../../.env --trace 1
python3 ../../tools/show_tables.py --config annexure_config.xlsx --env ../../.env --limit 5
```

Result: `13 tables + 2 control tables`, then `file_id 1: 217 rows`:

```
summary                         9 rows from Summary!12-20
payout_breakup                 30 rows from Payout Breakup!7-42
order_level                   122 rows from Order Level!4-220
complaint_status               14 rows from Unresolved Customer Complaints!2-16
complaint_orders                0 rows from Unresolved Customer Complaints!22-222
adjustments_current             0 rows from Growth Investments and Other De!12-12
adjustments_previous            0 rows from Growth Investments and Other De!15-15
ads_investments_current         1 rows from Growth Investments and Other De!31-32
ads_investments_previous        0 rows from Growth Investments and Other De!35-35
recoveries                      0 rows from Growth Investments and Other De!47-199
discount_summary_swiggy        11 rows from Discount Summary!4-14
discount_summary_toing          3 rows from Discount Summary!18-20
glossary                       27 rows from Glossary!3-29
```

A block loading 0 rows is not a failure - the configured range holds no records
this week. The range used is recorded in `load_config_audit` either way.

Both targets give the same 217 rows; the PostgreSQL run only differs in the
last line and in the placeholders inside the `INSERT` (`%s` instead of `?`):

```
read 6 setting(s) from .env: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
...
file_id 1: 222 rows into postgres excel_parser (schema swiggy)
```

This file also carries one genuinely dirty cell - `75.4` under
"Cancellation time" - which is reported instead of breaking the load:

```
1 cell(s) did not match their configured data_type:
  order_level: Order Level!AV78 -> cancellation_time stored as NULL, '75.4' is not a date
```

## How one Swiggy order is pushed

```
Order Level!4 -> order_level
  A4      245185478129821      -> order_id               '245185478129821'
  C4      2026-08-09 00:34:38  -> order_date             '2026-08-09 00:34:38'
  D4      delivered            -> order_status           'delivered'
  E4      Swiggy               -> order_category         'Swiggy'
  I4      398.0                -> item_total             398.0
  S4      79.8                 -> commission             79.8
  AM4     205.76               -> net_payout_for_order   205.76
  ...
  INSERT INTO order_level (file_id, sheet_name, source_row_num, order_id, ... )
  VALUES (?, ?, ?, ?, ... )
  params: [1, 'Order Level', 4, '245185478129821', ... ]
```

51 cells of worksheet row 4 -> 51 columns, plus `file_id=1`,
`sheet_name='Order Level'`, `source_row_num=4`. One parameterised statement, no
cell value inside the SQL text.

## Checking the Swiggy numbers

The queries below are the same on SQLite and PostgreSQL:

```sql
SELECT order_category, order_status, COUNT(*) AS orders,
       ROUND(SUM(net_payout_for_order), 2) AS net_payout
FROM order_level GROUP BY order_category, order_status;
```

```
order_category  order_status  orders  net_payout
Swiggy          delivered     80      21233.1
Toing           cancelled     1       255.75
Toing           delivered     39      6719.98
XL order        delivered     2       993.21
```

Reconciliation against the file's own Summary sheet - 80 Swiggy + 2 XL:

```sql
SELECT (SELECT COUNT(*) FROM order_level
        WHERE order_category IN ('Swiggy', 'XL order')) AS order_level_rows,
       (SELECT field_value FROM summary
        WHERE field_label LIKE 'Total orders on Swiggy%')  AS summary_says;
```

```
order_level_rows  summary_says
82                82
```

The payout breakup, still row-addressable:

```sql
SELECT source_row_num, line_ref, particulars, swiggy_delivered, total_amount
FROM payout_breakup ORDER BY source_row_num LIMIT 10;
```

```
source_row_num  line_ref  particulars                          swiggy_delivered  total_amount
7                         Orders                               82                122
8               A         Total Customer Paid [1+2-3-4+5]      35643.09          44650.87
9               1.0       Item Total                           37896             46642.7
...
16              6.0       Commission                           -8910.91          -10262.06
```

Each of those numbers points back at a cell: table + `sheet_name` +
`source_row_num` + the `col:` letter in `column_config`.

## The one naming point worth knowing

`Payout Breakup` prints "Delivered Orders" and "Cancelled Orders" twice - once
for Swiggy, once for Toing. Two Excel columns cannot share a database column
name, so `column_config` maps them to `swiggy_delivered` / `swiggy_cancelled`
and `toing_delivered` / `toing_cancelled`, with `source_header` keeping the
printed text.

## Next month's file

```bash
python3 ../../tools/executor.py annexure_config.xlsx <next-file>.xlsx
#   ... or --target postgres --env .env
```

Same database, new `file_id`; both loads stay separately queryable. Only a
layout change by Swiggy means touching the configuration - row ranges and `col:`
letters - never the code.

---

# Example 16 — source_ref showcase

*Folder: `examples/16_source_ref_showcase/`*

All four `source_ref` types in a single table: `col:`, `const:`, `fn:`, and
`expr:`. Also demonstrates parentheses, unary minus, NULL propagation, and
all five `fn:` functions.

## Source: `products_source.xlsx`

| Product | Category | Price | Qty | Tax % | Discount |
|---|---|---|---|---|---|
| Widget A | Electronics | 499.99 | 10 | 18 | 50 |
| Gadget B | Electronics | 1299.50 | 5 | 18 | *(empty)* |
| Book C | Stationery | 89.00 | 25 | 5 | 10 |
| Pen D | Stationery | 15.50 | 100 | 5 | *(empty)* |

Rows 2 and 4 have empty Discount — this tests NULL propagation in expressions.

## Configuration

`column_config` — 20 columns covering all features:

| column_name | source_ref | what it demonstrates |
|---|---|---|
| product | `col:A` | **col:** read from Excel |
| category | `col:B` | **col:** read from Excel |
| price | `col:C` | **col:** read from Excel |
| qty | `col:D` | **col:** read from Excel |
| tax_pct | `col:E` | **col:** read from Excel |
| discount | `col:F` | **col:** some rows are NULL |
| currency | `const:INR` | **const:** fixed value |
| warehouse | `const:warehouse-1` | **const:** fixed value |
| loaded_at | `fn:now` | **fn:** current timestamp |
| load_date | `fn:today` | **fn:** current date |
| row_id | `fn:uuid` | **fn:** unique UUID per row |
| source_file | `fn:file_name` | **fn:** source file name |
| row_num | `fn:sequence` | **fn:** auto-counter 1,2,3,4 |
| subtotal | `expr:{C} * {D}` | **expr:** basic arithmetic |
| tax_amount | `expr:{C} * {D} * {E} / 100` | **expr:** chained arithmetic |
| total | `expr:({C} * {D}) + ({C} * {D} * {E} / 100)` | **expr:** parentheses |
| net_discount | `expr:{C} * {D} - {F}` | **expr:** NULL propagation (NULL when discount empty) |
| neg_discount | `expr:-{F}` | **expr:** unary minus (NULL when discount empty) |
| label | `expr:{A} & " (" & {B} & ")"` | **expr:** string concatenation |
| price_label | `expr:{A} & " - " & const:INR & " " & {C}` | **expr:** mix col + const in concat |

## Run

```bash
cd examples/16_source_ref_showcase
python3 ../../tools/validator.py products_config.xlsx products_source.xlsx --ddl schema.sqlite.sql --target sqlite
python3 ../../tools/executor.py  products_config.xlsx products_source.xlsx --target sqlite --database products.db --trace 2
```

Expected: 4 rows, 0 errors, 0 warnings.

## Key behaviors

| Feature | Column | Rows 1,3 (Discount filled) | Rows 2,4 (Discount NULL) |
|---|---|---|---|
| NULL propagation | net_discount | `subtotal - 50` = 4949.9 | NULL (arithmetic with NULL → NULL) |
| Unary minus | neg_discount | `-50` | NULL |
| Parentheses | total | `(price*qty) + (price*qty*tax/100)` | same (no NULL in this expr) |
| fn:sequence | row_num | 1, 3 | 2, 4 |
| fn:uuid | row_id | a different UUID for every row | a different UUID for every row |
| fn:file_name | source_file | `products_source.xlsx` | `products_source.xlsx` |

---

# Example 17 — kitchen sink (comprehensive regression test)

*Folder: `examples/17_kitchen_sink/`*

Every parser feature in a single file. Use this as a regression test — if it
validates and loads correctly, the parser is working.

## Source: `sink_source.xlsx` (4 sheets)

| Sheet | Rows | Purpose |
|---|---|---|
| Orders | 6 data rows | main table — all 6 data types, messy values (₹, brackets, NA) |
| Items | 8 data rows | child table — FK to orders via order_id |
| Summary | 5 rows | key_value layout — label/value pairs |
| Archive | 1 row | exists but active=N — completely skipped |

## Configuration: `sink_config.xlsx`

### target_config
postgres, database `excel_parser`, schema `kitchen_sink`, prefix `ks_`, id_type `uuid`.

### sheet_config (4 blocks, 1 inactive)

| table | sheet | layout | row_filter | active |
|---|---|---|---|---|
| orders | Orders | table | `col:D = "Active"` | Y |
| items | Items | table | *(none)* | Y |
| summary | Summary | key_value | *(none)* | Y |
| archive | Archive | table | *(none)* | **N** |

### Features covered per column

**orders** (24 columns):

| # | Feature | Column | Detail |
|---|---|---|---|
| 1 | col: + text + is_key + script | order_id | `trim\|uppercase` |
| 2 | col: + text + script | customer | `trim\|titlecase` |
| 3 | col: + date + date_format | order_date | `%m/%d/%Y` pins MM/DD |
| 4 | col: + text + script | status | `trim\|lowercase` |
| 5 | col: + numeric + null_default | subtotal | handles `₹`, `(negative)`, null_default=0 |
| 6 | col: + numeric + null_default | tax_pct | null_default=0 |
| 7 | col: + numeric + null_default | discount | NULL → 0 via null_default |
| 8 | col: + boolean | is_paid | yes/no/true/false/1/0/maybe |
| 9 | col: + text + null_default | notes | null_default=N/A |
| 10 | fn:now | loaded_at | timestamp |
| 11 | fn:today | load_date | date |
| 12 | fn:uuid | row_uuid | unique per row |
| 13 | fn:file_name | source_file | source file name |
| 14 | fn:sequence | row_num | 1,2,3,4,5 |
| 15 | const: | currency | INR |
| 16 | const: | api_version | v2 |
| 17 | expr: + column name ref + script | tax_amount | `{subtotal} * {tax_pct} / 100`, round_2 |
| 18 | expr: + column name ref | gross_total | `{subtotal} + {tax_amount}` |
| 19 | expr: + NULL propagation | net_total | `{gross_total} - {discount}` |
| 20 | expr: + unary minus | neg_discount | `-{discount}` |
| 21 | expr: + parentheses + literal | surcharge_1pct | `({subtotal} + {tax_amount}) * 0.01`, round_2 |
| 22 | expr: + string concat | order_label | `{A} & " — " & {B}` |
| 23 | expr: + fn in expr | id_with_date | `{A} & " " & fn:today` |
| 24 | col: (duplicate) + date_format + script | order_month | same col:C, `year_month` script |

**items** (8 columns): FK `references` to orders.order_id, `clamp_0` script,
`%d-%b-%Y` date_format, expr `{qty} * {unit_price}` with column name refs,
`fn:sequence` (resets per table), `const:piece`.

**summary** (4 columns): key_value layout, `map:` positional labels
(`field_name`), `trim` script, `fn:now`.

**archive**: active=N — no table created, no data loaded.

## Run

```bash
cd examples/17_kitchen_sink
python3 ../../tools/validator.py sink_config.xlsx sink_source.xlsx --ddl schema.sqlite.sql --target sqlite
python3 ../../tools/executor.py  sink_config.xlsx sink_source.xlsx --target sqlite --database sink.db --trace 2
```

Expected: **18 rows** (5 orders + 8 items + 5 summary), 0 errors, 4 warnings.

## Feature checklist

| Feature | Where it's tested |
|---|---|
| All 6 data types | orders: text, numeric, integer (fn:sequence), date, timestamp, boolean |
| source_ref col: | orders columns 1-9, items columns 1-5 |
| source_ref const: | orders.currency, orders.api_version, items.unit |
| source_ref fn:now | orders.loaded_at |
| source_ref fn:today | orders.load_date |
| source_ref fn:uuid | orders.row_uuid |
| source_ref fn:file_name | orders.source_file |
| source_ref fn:sequence | orders.row_num (1-5), items.line_num (1-8, resets) |
| source_ref expr: arithmetic | orders.tax_amount, orders.gross_total |
| source_ref expr: column name refs | `{subtotal}`, `{tax_amount}`, `{qty}`, `{unit_price}` |
| source_ref expr: parentheses | orders.surcharge_1pct |
| source_ref expr: unary minus | orders.neg_discount |
| source_ref expr: string concat | orders.order_label, orders.price_label |
| source_ref expr: fn in expr | orders.id_with_date |
| source_ref expr: NULL propagation | orders.net_total (when subtotal is negative) |
| row_filter | orders: `col:D = "Active"` filters out ORD-003 |
| date_format | orders.order_date `%m/%d/%Y`, items.item_date `%d-%b-%Y` |
| null_default | orders.subtotal=0, discount=0, notes=N/A |
| references (FK) | items.order_id → orders.order_id |
| is_key | orders.order_id, items.order_id |
| scripts (text) | trim, uppercase, titlecase, lowercase |
| scripts (numeric) | round_2, clamp_0 |
| scripts (date) | year_month |
| source_ref map: | summary.field_name: positional labels for key_value rows |
| key_value layout | summary table |
| active=N | archive table — skipped entirely |
| table_prefix | `ks_` on all tables |
| id_type=uuid | UUID primary keys |
| messy values | ₹ currency, (bracketed) negatives, NA dates, mixed boolean |
| data_start_row / data_end_row | orders 2-7, items 2-9, summary 1-5 |
| description / domain | on every sheet_config row |
