---
name: check-parser
description: Run every Excel Parser check — pyflakes, Angular build, all 17 examples through validator and executor with expected row counts, and push to PostgreSQL. Use after changing anything in tools/ or app/.
---

# Check the Excel Parser

Run from the project root. A change is not done until all checks pass.

## 1. Code quality

```bash
python3 -m pyflakes tools app/backend
(cd app/frontend && npm run build)        # Node 22+ on PATH
```

## 2. Test all examples

The test script validates and pushes every example to PostgreSQL, comparing
row counts against expected values. Examples 07 and 08 must fail validation.

```bash
./util/test-examples.sh              # validate + push all examples
./util/test-examples.sh --validate   # validate only, no push
```

Requires PG credentials in `.env` (or environment variables).

## 3. Expected row counts

| example | expect |
| --- | --- |
| 01_simple | 3 rows |
| 02_features | 12 rows |
| 03_uuid_keys | 4 rows (UUID keys) |
| 04_postgres_schema | 4 rows, schema `staging`, prefix `stg_` |
| 05_data_types | 4 rows (all 6 data types) |
| 06_references | 9 rows (3 orders + 6 items, FK) |
| 07_validation_errors | must fail validation |
| 08_source_mismatch | must fail validation |
| 09_swiggy_annexure | 217 rows (client file, skipped if absent) |
| 10_zomato_settlement | (client file, skipped if absent) |
| 11_growthfalcons | 109 rows (client file, skipped if absent) |
| 12_petpooja_growth | 31 rows |
| 13_smartq_payment | 33 rows |
| 14_zomato_business | 470 rows (CSV source) |
| 15_magicpin_ledger | 1141 rows |
| 16_source_ref_showcase | 3 rows (col/const/fn/expr, row_filter, date_format) |
| 17_kitchen_sink | 18 rows (5 orders + 8 items + 5 summary — every feature) |

Re-loading a byte-identical file is refused by dedup — that is a pass, not a
bug. If the configuration format changed, regenerate the template and
re-annotate all examples first:

```bash
python3 tools/make_template.py template/config_template.xlsx
python3 tools/make_examples.py
```
