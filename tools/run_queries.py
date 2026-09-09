"""Run a file of SELECT statements against the loaded database and print results.

    python run_queries.py queries.sql loaded.db
    python run_queries.py queries.sql --config annexure_config.xlsx --env .env
    python run_queries.py queries.sql --target postgres --env .env

Lines starting with "." (sqlite shell dot-commands) are ignored, so the same
file works on both targets.
"""
import argparse
import sqlite3
from pathlib import Path

import db as dbmod
import validator


def statements(text: str):
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("."))
    for chunk in body.split(";"):
        sql = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--"))
        if sql.strip():
            yield sql.strip(), chunk.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("queries")
    ap.add_argument("database", nargs="?", help="SQLite file; omit for --target postgres")
    ap.add_argument("--database", dest="database_opt", default=None,
                    help="same as the positional argument")
    ap.add_argument("--config", default=None,
                    help="configuration workbook to read target_config from")
    ap.add_argument("--target", choices=("sqlite", "postgres"), default=None)
    ap.add_argument("--env", default=".env")
    ap.add_argument("--prefix", default=None)
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

        def query(sql):
            return con.execute(sql)
    else:
        dbmod.load_env(Path(args.env))
        target = dbmod.PostgresTarget(where.prefix, where.database, where.db_schema)
        con = target.con

        def query(sql):
            cur = con.cursor()
            cur.execute(sql)
            return cur

    for sql, original in statements(Path(args.queries).read_text(encoding="utf-8")):
        title = next((l for l in original.splitlines() if l.strip().startswith("--")), "")
        print("\n" + (title.strip() or sql.splitlines()[0]))
        cur = query(sql)
        head = [d[0] for d in cur.description]
        rows = cur.fetchall()
        widths = [max(len(h), *([len(str(r[i])) for r in rows] or [0]))
                  for i, h in enumerate(head)]
        print("  ".join(h.ljust(w) for h, w in zip(head, widths)))
        for row in rows:
            print("  ".join(str(v).ljust(w) for v, w in zip(row, widths)))
    con.close()


if __name__ == "__main__":
    main()
