---
name: check-parser
description: Run every Excel Parser check — pyflakes, backend tests, Angular build, and all eight examples through validator and executor — and compare against the expected row counts. Use after changing anything in tools/ or app/.
---

# Check the Excel Parser

Run from the project root. Do all four; a change is not done until they pass.

```bash
python3 -m pyflakes tools app/backend
(cd app/backend && python3 -m pytest -q)
(cd app/frontend && npm run build)        # Node 22 on PATH
```

Then the examples. Work in a scratch directory (the example folders hold only
the two workbooks — everything else is produced), and note that `executor.py`
reads the DDL file the validator wrote from the *working directory*:

```bash
work=$(mktemp -d)
cd "$work"
cp /path/to/excel_parser/examples/01_simple/*.xlsx .
python3 /path/to/excel_parser/tools/validator.py sales_config.xlsx sales_source.xlsx \
        --ddl schema.postgres.sql
python3 /path/to/excel_parser/tools/executor.py sales_config.xlsx sales_source.xlsx
```

Repeat for each example and check the count:

| example | expect |
| --- | --- |
| 01_simple | 3 rows |
| 02_features | 12 rows |
| 03_uuid_keys | 4 rows, unique valid UUIDs, `file_id` joins intact |
| 04_postgres_schema | 4 rows into PostgreSQL, schema `staging`, prefix `stg_` (needs `.env`) |
| 05_data_types | 4 rows |
| 06_references | 9 rows (3 orders + 6 items) |
| 07_validation_errors | must fail validation, exit 1, nothing written |
| 08_source_mismatch | must fail validation, exit 1, nothing written |
| 09_swiggy_annexure | 217 rows, `order_level` 122, four blocks legitimately 0 rows, `Order Level!AV78` reported and stored NULL |
| 11_growthfalcons | 109 rows, 5 tables |

Re-loading a byte-identical file is refused by design — that is a pass, not a
bug. If the configuration format changed, also regenerate
`template/config_template.xlsx` with `tools/make_template.py` and re-annotate
every example configuration (`--annotate`) before running the above.
