"""Stage 2 - push a source workbook into the database. Dumping only.

    # target, database, schema and prefix come from the workbook's target_config
    python executor.py config.xlsx source.xlsx

    # any of them can be overridden, and PostgreSQL credentials come from .env
    python executor.py config.xlsx source.xlsx --target postgres --env .env

The executor makes no judgements: validator.py has already decided the pair is
loadable, so this reads the configured cells, casts them, and inserts. Every
row carries file_id / sheet_name / source_row_num, and every value is bound as
a query parameter.

By default the configuration is re-validated first and errors abort the run
before anything is written (`--no-validate` skips that, e.g. when a UI has just
validated the same pair).

For an application later: call `execute(...)` and read the returned LoadResult;
pass a `log=` callable to receive the progress lines instead of stdout.
"""
import argparse
import datetime as dt
import hashlib
import uuid
from collections import namedtuple
from pathlib import Path

import openpyxl

import db as dbmod
import rows as rowmod
import validator

LoadResult = namedtuple("LoadResult", "file_id total per_table skipped_rows bad_cells target")

# Defaults for orphaned columns (exist in DB but removed from config).
# New rows get these values instead of failing on a missing column.
_NUMERIC_TYPES = {"numeric", "decimal", "real", "double precision", "float",
                  "integer", "bigint", "smallint", "int", "int4", "int8", "int2"}
_BOOL_TYPES = {"boolean", "bool"}


def _type_default(db_type: str):
    """Return a sensible default for a database column type."""
    t = db_type.lower().strip()
    if t in _NUMERIC_TYPES:
        return 0
    if t in _BOOL_TYPES:
        return False
    return None      # text, date, timestamp → NULL


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def execute(config: Path, source: Path, target: str = None, database=None, prefix: str = None,
            schema_sql: str = None, trace: int = 0, log=print, id_type: str = None,
            strict: bool = False, source_ref: str = None, config_ref: str = None,
            skip_audit: bool = False) -> LoadResult:
    """Insert every configured row of `source` into the configured target.

    `target`, `database`, `prefix` and `id_type` override the workbook's
    target_config; leave them None to use what the configuration says.

    With `id_type = uuid` the keys are UUIDs generated here rather than by the
    database, so a row keeps the same key on either target.
    """
    sheets, columns = validator.read_config(config)
    where = validator.resolve_target(config, target, database, prefix, id_type)
    prefix = where.prefix
    uuid_keys = where.id_type == "uuid"
    import csv_adapter
    wb = csv_adapter.open_source(source)

    dbmod.ident(f"{prefix}x", "table_prefix")
    con = dbmod.connect(where.target, where.database, prefix, where.db_schema)
    ph = con.ph
    if schema_sql:
        try:
            con.ensure_schema(schema_sql)
        except Exception as exc:
            con.close()
            raise SystemExit(
                f"the schema file does not fit {where.target} {con.label}: {exc}\n"
                "regenerate it with validator.py --ddl for this target and prefix, or "
                "point the configuration at a database/schema of its own") from exc

    wanted = [dbmod.ident(f"{prefix}{str(s['table_name']).strip()}", "table_name")
              for s in sheets]
    if not skip_audit:
        wanted.append(f"{prefix}load_config_audit")
    absent = con.missing_tables(wanted)
    if absent:
        con.close()
        raise SystemExit(f"these tables are not in {where.target} {con.label}: "
                         + ", ".join(absent)
                         + "\napply the DDL from validator.py --ddl, or point the "
                           "configuration at a database/schema of its own")

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    # Dedup: check if this exact file was already loaded (only when audit is on)
    if not skip_audit:
        try:
            if where.target == "postgres":
                with con.con.cursor() as cur:
                    cur.execute(f"SELECT 1 FROM {prefix}load_config_audit "
                                "WHERE file_sha256 = %s LIMIT 1", (digest,))
                    if cur.fetchone():
                        con.close()
                        raise SystemExit(f"{source.name} has already been loaded into this "
                                         "database (identical content); nothing was inserted")
            else:
                row = con.con.execute(
                    f"SELECT 1 FROM {prefix}load_config_audit WHERE file_sha256 = ? LIMIT 1",
                    (digest,)).fetchone()
                if row:
                    con.close()
                    raise SystemExit(f"{source.name} has already been loaded into this "
                                     "database (identical content); nothing was inserted")
        except SystemExit:
            raise
        except Exception:
            pass  # table might be empty or not yet created

    # Generate a file_id for this load (UUID string, always unique)
    file_id = str(uuid.uuid4())

    total, per_table, skipped_rows, bad_cells = 0, {}, [], []
    try:
        for sheet in sheets:
            table = dbmod.ident(f"{prefix}{str(sheet['table_name']).strip()}", "table_name")
            name = str(sheet["sheet_name"]).strip()
            if name not in wb.sheetnames:
                continue
            ws = wb[name]
            cols = columns[sheet["table_name"]]
            header_row = sheet.get("header_row")
            start, end = rowmod.row_range(sheet, ws)

            # Detect orphaned columns: exist in DB but not in current config.
            # These get a type-appropriate default on every new row.
            config_col_names = {str(c["column_name"]).strip() for c in cols}
            lineage_cols = {"file_id", "file_name", "file_sha256", "source_ref",
                            "sheet_name", "source_row_num",
                            f"{str(sheet['table_name']).strip()}_id"}
            orphaned = []
            try:
                db_cols = con.table_columns(table)
                for db_col, db_type in db_cols.items():
                    if db_col in config_col_names or db_col in lineage_cols:
                        continue
                    default = _type_default(db_type)
                    orphaned.append((db_col, default))
                    default_desc = repr(default) if default is not None else "NULL"
                    log(f"  {table}.{db_col} not in config — new rows get {default_desc}")
            except Exception:
                pass

            key = dbmod.ident(f"{str(sheet['table_name']).strip()}_id", "column_name")
            lead = ([key] if uuid_keys else []) + [
                "file_id", "file_name", "file_sha256", "source_ref",
                "sheet_name", "source_row_num"]
            all_col_names = (lead
                             + [dbmod.ident(c["column_name"], "column_name") for c in cols]
                             + [dbmod.ident(o[0], "column_name") for o in orphaned])
            insert = (f"INSERT INTO {table} (" + ", ".join(all_col_names)
                      + ") VALUES (" + ", ".join([ph] * len(all_col_names)) + ")")
            loaded = 0
            row_ctx = {"file_name": source.name,
                        "_seq_key": str(sheet["table_name"]).strip()}
            # Parse where filter
            import validator as validmod
            where_clause = str(sheet.get("row_filter") or "").strip()
            where_conditions = validmod.parse_where(where_clause) if where_clause else []
            for row_num in range(start, end + 1):
                # Apply where filter
                if where_conditions:
                    from openpyxl.utils import column_index_from_string as _cis
                    def _where_reader(ltr, _ws=ws, _row=row_num):
                        return _ws.cell(_row, _cis(ltr)).value
                    if not validmod.evaluate_where(where_conditions, _where_reader):
                        continue
                read = rowmod.build_row(ws, cols, row_num, row_ctx)
                for ref, column, message in read.bad:
                    bad_cells.append(f"{table}: {name}!{ref} -> {column} stored as NULL, "
                                     f"{message}")
                if read.empty:
                    continue
                if read.missing:
                    skipped_rows.append(f"{name}!{row_num}: empty required column(s) "
                                        f"{', '.join(read.missing)}")
                    log(f"  skip {skipped_rows[-1]}")
                    if strict:
                        continue
                    continue
                params = ([str(uuid.uuid4())] if uuid_keys else []) \
                    + [file_id, source.name, digest, source_ref,
                       name, row_num, *read.values] \
                    + [default for _, default in orphaned]
                if loaded < trace:
                    log(f"\n  {name}!{row_num} -> {table}")
                    for ref, raw, column, value in read.cells:
                        log(f"    {ref:<7} {str(raw)[:28]:<30} -> {column:<38} {value!r}")
                    log(f"    {insert}")
                    log(f"    params: {params}")
                con.execute(insert, params)
                loaded += 1

            if not skip_audit:
                audit = (["audit_id"] if uuid_keys else []) + [
                    "file_id", "file_name", "file_sha256", "source_ref", "config_ref",
                    "table_name", "sheet_name", "header_row",
                    "data_start_row", "data_end_row", "column_count", "row_count", "loaded_at"]
                con.execute(
                    f"INSERT INTO {prefix}load_config_audit (" + ", ".join(audit) + ") "
                    "VALUES (" + ", ".join([ph] * len(audit)) + ")",
                    (([str(uuid.uuid4())] if uuid_keys else [])
                     + [file_id, source.name, digest, source_ref, config_ref,
                        table, name, header_row, start, end, len(cols), loaded, now()]))
            per_table[table] = loaded
            total += loaded
            log(f"{table:<32} {loaded:>4} rows from {name}!{start}-{end}")

        # In strict mode, refuse to commit if there are type mismatches.
        # Skipped rows (empty required columns) are logged but not blocking —
        # empty sections in multi-block sheets are normal.
        if strict and bad_cells:
            con.rollback()
            con.close()
            raise SystemExit(
                f"data quality check failed: {len(bad_cells)} value(s) don't match "
                f"their column type — nothing was written")

        con.commit()
    except SystemExit:
        raise
    except Exception:
        con.rollback()
        con.close()
        raise

    label = f"{con.name} {con.label}"
    con.close()
    return LoadResult(file_id, total, per_table, skipped_rows, bad_cells, label)


def main() -> None:
    ap = argparse.ArgumentParser(description="push a source workbook into the database")
    ap.add_argument("config")
    ap.add_argument("source")
    ap.add_argument("database", nargs="?",
                    help="SQLite file path / PostgreSQL database name; "
                         "default target_config[database]")
    ap.add_argument("--database", dest="database_opt", default=None,
                    help="same as the positional argument")
    ap.add_argument("--target", choices=("sqlite", "postgres"), default=None,
                    help="override target_config[target]")
    ap.add_argument("--env", default=".env",
                    help="file with the PostgreSQL credentials (default .env); real "
                         "environment variables take precedence")
    ap.add_argument("--prefix", default=None, help="override target_config[table_prefix]")
    ap.add_argument("--id-type", choices=validator.ID_TYPES, default=None,
                    help="override target_config[id_type] - integer keys or UUID keys")
    ap.add_argument("--schema", default=None,
                    help="DDL file to apply if the tables do not exist yet "
                         "(default schema.sqlite.sql / schema.postgres.sql)")
    ap.add_argument("--no-validate", action="store_true",
                    help="skip the validator (only when it has just been run)")
    ap.add_argument("--trace", type=int, default=0, metavar="N",
                    help="print the cell -> column mapping and the INSERT for the first N rows "
                         "of every table")
    args = ap.parse_args()

    config, source = Path(args.config), Path(args.source)
    args.database = args.database_opt or args.database
    where = validator.resolve_target(config, args.target, args.database, args.prefix,
                                     args.id_type)

    if not args.no_validate:
        errors = [i for i in validator.validate(config, source, args.prefix, args.target,
                                                args.database, args.id_type)
                  if i.severity == "error"]
        if errors:
            for issue in errors[:40]:
                print(f"ERROR    {issue.where}: {issue.message}")
            raise SystemExit(f"{len(errors)} error(s) - nothing was pushed. Run validator.py "
                             f"for the full report.")

    if where.target == "postgres":
        keys = dbmod.load_env(Path(args.env))
        if keys:
            print(f"read {len(keys)} setting(s) from {args.env}: "
                  + ", ".join(k for k in keys if k in dbmod.ENV_KEYS))

    schema_file = Path(args.schema or f"schema.{where.target}.sql")
    if not schema_file.exists():
        raise SystemExit(f"{schema_file} not found - run validator.py --ddl {schema_file} first")

    result = execute(config, source, args.target, args.database, args.prefix,
                     schema_file.read_text(), args.trace, id_type=args.id_type)

    if result.bad_cells:
        print(f"\n{len(result.bad_cells)} cell(s) did not match their configured data_type:")
        for line in result.bad_cells[:20]:
            print(f"  {line}")
        if len(result.bad_cells) > 20:
            print(f"  ... and {len(result.bad_cells) - 20} more")
    print(f"file_id {result.file_id}: {result.total} rows into {result.target}")


if __name__ == "__main__":
    main()
