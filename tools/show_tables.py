"""Print every loaded table of a database produced by executor.py.

    python show_tables.py sales.db --limit 20
    python show_tables.py --config sales_config.xlsx --env .env    # same target as the load
    python show_tables.py --target postgres --env .env --limit 5

Handy for checking what actually landed after a load.
"""
import argparse
import os
import sqlite3
from pathlib import Path

import db as dbmod
import validator


def sqlite_tables(con):
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("database", nargs="?", help="SQLite file; omit for --target postgres")
    ap.add_argument("--database", dest="database_opt", default=None,
                    help="same as the positional argument")
    ap.add_argument("--config", default=None,
                    help="configuration workbook to read target_config from")
    ap.add_argument("--target", choices=("sqlite", "postgres"), default=None)
    ap.add_argument("--env", default=".env")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    args.database = args.database_opt or args.database

    where = (validator.resolve_target(Path(args.config), args.target, args.database, args.prefix)
             if args.config else
             validator.Target(args.target or "sqlite", args.database, None,
                              args.prefix or ""))

    if where.target == "sqlite":
        if not where.database:
            raise SystemExit("give the SQLite file path, or use --target postgres")
        con = sqlite3.connect(where.database)
        tables = sqlite_tables(con)
        query = con.execute
    else:
        dbmod.load_env(Path(args.env))
        target = dbmod.PostgresTarget(where.prefix, where.database, where.db_schema)
        schema = where.db_schema or os.environ.get("PGSCHEMA", "public")
        with target.con.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = %s ORDER BY table_name", (schema,))
            tables = [r[0] for r in cur.fetchall()]
        print(f"-- postgres {target.label}")

        def query(sql, params=()):
            cur = target.con.cursor()
            cur.execute(sql, params)
            return cur
        con = target.con

    for table in map(dbmod.ident, tables):
        cur = query(f"SELECT * FROM {table} LIMIT {int(args.limit)}")
        head = [d[0] for d in cur.description]
        rows = cur.fetchall()
        count = query(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"\n=== {table}  ({count} rows) ===")
        if not rows:
            continue
        widths = [max(len(h), *[len(str(r[i])) for r in rows]) for i, h in enumerate(head)]
        print("  ".join(h.ljust(w) for h, w in zip(head, widths)))
        for row in rows:
            print("  ".join(str(v).ljust(w) for v, w in zip(row, widths)))
    con.close()


if __name__ == "__main__":
    main()
