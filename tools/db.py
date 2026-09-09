"""Database targets for the loader: SQLite (default) or PostgreSQL.

Both targets expose the same three things, so the loader itself never knows
which database it is talking to:

    ph                      the parameter placeholder ("?" or "%s")
    ensure_schema(sql)      run the generated DDL once, if the tables are absent
    execute(sql, params)    parameterised statement
    insert_returning_id()   insert one row and return its generated id

The configuration workbook may name the target, the database and the schema
(`target_config`). Credentials never come from there: host, user and password
are read from the environment (a .env file) only, never from the code, the
command line or the workbook.
"""
import os
import re
import sqlite3
from pathlib import Path

ENV_KEYS = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE", "DATABASE_URL")

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ident(name, what: str = "identifier") -> str:
    """Allow a plain unquoted SQL name only.

    Table, column and schema names come from the configuration workbook or the
    environment, so they cannot be bound as parameters; they are checked against
    this allowlist before they ever reach SQL text.
    """
    text = str(name).strip()
    if not IDENTIFIER.match(text) or len(text) > 63:
        raise SystemExit(
            f"invalid {what} {name!r}: letters, digits and underscores only, "
            f"starting with a letter or underscore, at most 63 characters"
        )
    return text


def load_env(path: Path) -> list:
    """Read KEY=VALUE lines from a .env file into os.environ (existing values win).

    Returns the names of the keys that were set, never the values.
    """
    if not path.exists():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
        found.append(key)
    return found


class SqliteTarget:
    ph = "?"
    name = "sqlite"

    def __init__(self, database: str):
        self.path = Path(database)
        self.fresh = not self.path.exists()
        self.con = sqlite3.connect(self.path)
        self.label = str(self.path)

    def ensure_schema(self, sql: str) -> None:
        if self.fresh:
            self.con.executescript(sql)

    def missing_tables(self, tables) -> list:
        present = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        return [t for t in tables if t not in present]

    def execute(self, sql: str, params=()) -> None:
        self.con.execute(sql, params)

    def insert_returning_id(self, sql: str, params, id_column: str):
        return self.con.execute(sql, params).lastrowid

    def commit(self) -> None:
        self.con.commit()

    def rollback(self) -> None:
        self.con.rollback()

    def close(self) -> None:
        self.con.close()


class PostgresTarget:
    ph = "%s"
    name = "postgres"

    def __init__(self, prefix: str, database=None, db_schema=None):
        try:
            import psycopg
        except ImportError as exc:                                  # pragma: no cover
            raise SystemExit("postgres target needs psycopg: pip install 'psycopg[binary]'") from exc

        dbname = database or os.environ.get("PGDATABASE")
        url = os.environ.get("DATABASE_URL")
        if url:
            self.con = psycopg.connect(url)
            if database:
                with self.con.cursor() as cur:
                    cur.execute("SELECT current_database()")
                    connected = cur.fetchone()[0]
                if connected != database:
                    self.con.close()
                    raise SystemExit(
                        f"the configuration targets database {database!r} but DATABASE_URL "
                        f"connects to {connected!r} - point them at the same database")
        else:
            missing = [k for k in ("PGHOST", "PGUSER", "PGPASSWORD") if not os.environ.get(k)]
            if not dbname:
                missing.append("PGDATABASE")
            if missing:
                raise SystemExit(
                    "missing PostgreSQL settings in the environment/.env: "
                    + ", ".join(missing) + " (or set DATABASE_URL)")
            self.con = psycopg.connect(
                host=os.environ["PGHOST"], port=os.environ.get("PGPORT", "5432"),
                dbname=dbname, user=os.environ["PGUSER"],
                password=os.environ["PGPASSWORD"],
                sslmode=os.environ.get("PGSSLMODE", "prefer"),
            )
        schema = db_schema or os.environ.get("PGSCHEMA")
        if schema:
            schema = ident(schema, "PGSCHEMA")
            with self.con.cursor() as cur:
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                cur.execute(f'SET search_path TO "{schema}"')
            self.con.commit()
        self.prefix = prefix
        self.label = f"{dbname or 'postgres'}"
        if schema:
            self.label += f" (schema {schema})"

    def ensure_schema(self, sql: str) -> None:
        with self.con.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f"{self.prefix}load_config_audit",))
            if cur.fetchone()[0] is None:
                cur.execute(sql)
        self.con.commit()

    def missing_tables(self, tables) -> list:
        missing = []
        with self.con.cursor() as cur:
            for table in tables:
                cur.execute("SELECT to_regclass(%s)", (table,))
                if cur.fetchone()[0] is None:
                    missing.append(table)
        return missing

    def execute(self, sql: str, params=()) -> None:
        with self.con.cursor() as cur:
            cur.execute(sql, params)

    def insert_returning_id(self, sql: str, params, id_column: str):
        with self.con.cursor() as cur:
            cur.execute(f"{sql} RETURNING {ident(id_column, 'id column')}", params)
            return cur.fetchone()[0]

    def commit(self) -> None:
        self.con.commit()

    def rollback(self) -> None:
        self.con.rollback()

    def close(self) -> None:
        self.con.close()


def connect(target: str, database, prefix: str, db_schema=None):
    if target == "sqlite":
        if not database:
            raise SystemExit("the sqlite target needs a database file path - set it in the "
                             "target_config sheet or pass it on the command line")
        return SqliteTarget(database)
    return PostgresTarget(prefix, database, db_schema)
