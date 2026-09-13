# How to run the excel parser, step by step

## Step 0 - one-time setup

```bash
python3 -m pip install openpyxl                  # reading the workbooks
python3 -m pip install "psycopg[binary]"         # only for --target postgres
```

SQLite needs nothing else (it is in the Python standard library).

Everything below is run from inside an example folder; `../../tools/...` points
at the scripts. Nothing writes outside the folder you run it in.

---

## Step 1 - have the two workbooks ready

| File | What it is |
|---|---|
| `*_source.xlsx` | the source excel you received (the data) |
| `*_config.xlsx` | the configuration excel (`target_config` + `sheet_config` + `column_config`) |

Each example folder already contains exactly this pair, and nothing else:

```bash
cd examples/01_simple
ls                                 # sales_source.xlsx  sales_config.xlsx
```

For your own file, start from the template - it holds the three sheets with
every header explained (hover a header for its note, or read the `help_*`
sheets) plus one example block that already loads:

```bash
cp template/config_template.xlsx my_config.xlsx     # then edit the three sheets
python3 tools/make_template.py template/config_template.xlsx   # to regenerate it
python3 tools/make_template.py my_config.xlsx --annotate       # put the notes on an
                                                               # existing workbook
```

Every example configuration carries the same notes, so any of them works as a
starting point too - `docs/EXAMPLES.md` opens with a scenario table naming the
example that shows each feature (UUID keys, a PostgreSQL schema and prefix, all
the data types, and two examples that deliberately fail validation).

`tools/bootstrap_config.py` generated the Swiggy configuration in
`examples/09_swiggy_annexure`. It is not a generic detector: the block list
(sheet, header row, row range) is declared in its `BLOCKS` constant and the
column names are guessed from the headers on those rows.

```bash
python3 ../../tools/bootstrap_config.py <source.xlsx> my_config.xlsx
```

Use it only after editing `BLOCKS` for the file you have, or simply copy an
example config workbook and edit the two sheets by hand - that is the normal
route. Either way, check the result against `docs/CONFIG_RULES.md`.

The `target_config` sheet of that workbook says where the data goes, so most
commands below need no `--target` / database argument:

| setting | example | |
|---|---|---|
| `target` | `postgres` | or `sqlite` |
| `database` | `excel_parser` | PostgreSQL database name, or SQLite file path |
| `db_schema` | `staging` | PostgreSQL only, created if absent |
| `table_prefix` | *(blank)* | prefix on every generated table; blank leaves the names as configured |
| `id_type` | `integer` | `integer` = database counter keys, `uuid` = a UUID per row (`--id-type` overrides it) |

Credentials are never in there - host, user and password come from `.env`
(step 3). `--target`, `--database` and `--prefix` override the sheet when you
need to point the same configuration at another database.

---

## Step 2 - validate (stage 1), and write the schema

```bash
python3 ../../tools/validator.py sales_config.xlsx                  # config only
python3 ../../tools/validator.py sales_config.xlsx sales_source.xlsx  # + this file
```

It starts by echoing the target it read from the workbook:

```
target: postgres excel_parser (schema sales), table prefix (none)
```

Nothing is written to any database in this step. The validator answers "can
this pair be pushed?" and ends with one line:

```
sales_config.xlsx + sales_source.xlsx: OK to load - 0 errors, 1 warning(s)
```

Exit code 0 means loadable, 1 means it is not. What it checks:

| Configuration | Source workbook (only when you pass one) |
|---|---|
| both `sheet_config` / `column_config` tabs exist, required fields filled | every configured `sheet_name` exists as a tab |
| `table_name` / `column_name` are usable, unique, not reserved lineage names | `col:` letters are inside the used range |
| `data_type` is one of the six supported types | every configured cell converts to its `data_type` |
| `data_start_row` / `data_end_row` / `header_row` are sane whole numbers | rows that would be skipped for an empty `nullable = N` column |
| `source_ref` is a valid reference (`col:`, `const:`, `fn:`, `expr:`, or `map:`) | tables that would load 0 rows |
| `row_filter` syntax is valid (if set) | |
| `layout`, `nullable`, `is_key` hold allowed values | |
| `target_config` names a real target, database, schema and prefix - and no credentials | |

`ERROR` blocks the push; `warning` is information (a totals row fenced off, a
block that is empty this month). Add `--ddl` once it is clean:

```bash
python3 ../../tools/validator.py sales_config.xlsx sales_source.xlsx \
        --ddl schema.postgres.sql
```

Output: `wrote schema.postgres.sql: 1 tables + 2 control tables (postgres)`. The
file is written only when there are no errors.

* the DDL flavour follows the configured target; `--dialect` forces one.
* `--prefix` overrides `target_config[table_prefix]`.
* `--id-type integer|uuid` overrides `target_config[id_type]`; pass the same
  value to `executor.py` so the rows match the DDL.

Open the `.sql` file - it is plain readable DDL, one `CREATE TABLE` per active
`sheet_config` row. Regenerate it every time the configuration changes.

---

## Step 3 - execute (stage 2), pushing the rows

The executor makes no judgements - it reads the configured cells, casts them and
inserts. It re-runs the validator first and writes nothing if there are errors:

```
ERROR    column_config[summary.order id]: column_name must be letters/digits/underscores, ...
3 error(s) - nothing was pushed. Run validator.py for the full report.
```

`--no-validate` skips that pre-check when you have just validated the same pair.

### Into PostgreSQL (default for all examples)

All examples target PostgreSQL. Copy `.env.example` to `.env` and fill in the
credentials:

```
PGHOST=...
PGPORT=5432
PGUSER=excel_parser_loader
PGPASSWORD=...
PGSSLMODE=require      # optional
PGDATABASE=excel_parser # optional if target_config[database] is set
PGSCHEMA=staging       # optional if target_config[db_schema] is set
# or a single DATABASE_URL=postgresql://user:pass@host:5432/excel_parser
```

```bash
python3 ../../tools/executor.py sales_config.xlsx sales_source.xlsx --env .env --trace 3
```

The workbook decides the database and schema; `.env` only proves who you are.
Notes:

* Real environment variables win over the `.env` file, so CI can inject them
  instead. Nothing is printed except the **names** of the settings that were
  read - never the password.
* Keep `.env` out of version control (a `.gitignore` is included).
* Give the loader its own database user with rights on its own schema; that is
  all it needs.

### Notes

* The DDL from step 2 is applied automatically **only if the tables are not
  there yet** (`source_file` is absent in the schema). Otherwise the load just
  appends with a new `file_id`.
* `--trace N` prints, for the first N rows of every table, each cell read, the
  column it maps to, the converted value, and the exact parameterised `INSERT`
  with its parameters (`%s` on PostgreSQL, `?` on SQLite). Use it to prove what
  happened.
* `--prefix`, `--target` and `--database` must match what step 2 generated the
  DDL for; leave them off and both stages read the same `target_config`.

What you see per table:

```
sales                           3 rows from Sales!2-4
  skip Items!5: empty required column(s) item_code
file_id 1: 3 rows into postgres excel_parser (schema sales)
```

Rows are skipped only when completely empty (silent) or when a `nullable = N`
column is empty (printed, as above). A single cell that cannot be converted to
its configured type is stored as `NULL` and listed at the end of the run:

```
1 cell(s) did not match their configured data_type:
  order_level: Order Level!AV78 -> cancellation_time stored as NULL, '75.4' is not a date
```

That is a signal to fix the `data_type` in the configuration (or to accept the
junk value as `text`). The validator predicts both of these in step 2, so you
see them before anything is written.

---

## Step 4 - look at what landed

```bash
python3 ../../tools/show_tables.py --config sales_config.xlsx --env .env --limit 20
python3 ../../tools/run_queries.py ../../queries/swiggy_checks.sql \
        --config annexure_config.xlsx --env .env
```

Useful checks:

```sql
SELECT * FROM source_file;         -- which file, how many rows, when
SELECT * FROM load_config_audit;   -- which row ranges were used
SELECT sheet_name, source_row_num, * FROM sales;  -- lineage on every row
```

---

## Step 5 - re-running

Start clean:

```bash
# PostgreSQL: DROP SCHEMA sales CASCADE;          (or drop the loaded tables)
```

Or keep the database and load the next month's file - it gets a new `file_id`
and both loads stay separately queryable. A byte-identical file is refused:

```
sales_source.xlsx has already been loaded into this database (identical content);
nothing was inserted
```

---

## Regression test

Run every example through validator and executor, comparing row counts:

```bash
./util/test-examples.sh              # validate + push all examples to PostgreSQL
./util/test-examples.sh --validate   # validate only, no push
```

14 examples tested (09-11 skipped if client files absent). Examples 07 and 08
must fail validation. All others must match their expected row count exactly.

---

## Using the two stages from your own code

Both stages are plain functions, which is the seam an application would use:

```python
import validator, executor

issues = validator.validate(Path("config.xlsx"), Path("source.xlsx"))   # prints nothing
if any(i.severity == "error" for i in issues):
    ...                                    # show issue.where / issue.message to the user
else:
    validator.write_ddl(Path("config.xlsx"), Path("schema.postgres.sql"), "postgres", "")
    result = executor.execute(Path("config.xlsx"), Path("source.xlsx"), "postgres",
                              schema_sql=Path("schema.postgres.sql").read_text(),
                              log=lambda line: None)
    result.total, result.per_table, result.skipped_rows, result.bad_cells
```

---

## Common errors

Most of these are reported by `validator.py` in step 2, before anything is
written; the rest come from the database itself.

| Message | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: openpyxl` | dependency missing | step 0 |
| `postgres target needs psycopg: ...` | driver missing | `pip install "psycopg[binary]"` |
| `missing PostgreSQL settings in the environment/.env: PGHOST, ...` | `.env` not found or incomplete | copy `.env.example`, fill it, pass `--env <path>` |
| `password authentication failed` / `could not translate host name` | wrong values in `.env` | check them with your DBA; the loader prints only the setting names |
| `permission denied for schema ...` | the loader's user cannot create tables | grant it, or set `PGSCHEMA` to a schema it owns |
| `... did not match their configured data_type` | junk value in a typed column | fix `data_type`, or accept the cell as `text` |
| `duplicate column name: x` | two `column_config` rows share a `column_name` in one table | rename one |
| `unknown data_type 'money'` | invalid `data_type` | use `text`/`numeric`/`integer`/`date`/`timestamp`/`boolean` |
| `NOT NULL constraint failed` | `nullable = N` on a column that is empty in the source | set it to `Y`, or fix the row range |
| table loads `0 rows` | wrong `sheet_name`, or the range points at headings | check the tab name and `data_start_row` |
| `UNIQUE constraint failed: ...ux_..._row` | the same worksheet row loaded twice under one `file_id` | two active blocks overlap - fix the ranges |
| nothing at all loads | `active` is not `Y` | set `active = Y` |
