"""The application's own database: users, sessions, projects, runs.

Stored in PostgreSQL (same server as the loaded data, separate schema).
Connection comes from the environment / .env — the same PGHOST/PGUSER/PGPASSWORD
the parser uses. The app tables live in their own schema (APP_SCHEMA, default 'app').
"""
import datetime as dt
import json
import os
import secrets
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

APP_DIR = Path(__file__).resolve().parent.parent          # .../excel_parser/app
PROJECT_ROOT = APP_DIR.parent                             # .../excel_parser

APP_SCHEMA = os.environ.get("APP_SCHEMA", "excelparser_config")

SCHEMA = """
CREATE TABLE IF NOT EXISTS "user" (
    user_id             TEXT PRIMARY KEY,
    username            TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts     INTEGER NOT NULL DEFAULT 0,
    locked_until        TEXT
);

CREATE TABLE IF NOT EXISTS session (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES "user"(user_id),
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS project (
    project_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES "user"(user_id),
    name            TEXT NOT NULL,
    source_ref      TEXT NOT NULL,
    config_ref      TEXT NOT NULL,
    target_json     TEXT,
    auto_render     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_render_at  TEXT,
    last_push_at    TEXT,
    source_sha256   TEXT,
    config_sha256   TEXT,
    render_json     TEXT
);

CREATE TABLE IF NOT EXISTS run (
    run_id        TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES project(project_id),
    user_id       TEXT NOT NULL REFERENCES "user"(user_id),
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,
    target        TEXT,
    database      TEXT,
    db_schema     TEXT,
    prefix        TEXT,
    file_id       TEXT,
    row_total     INTEGER,
    source_name   TEXT,
    config_name   TEXT,
    source_sha256 TEXT,
    config_sha256 TEXT,
    rows_json     TEXT,
    issues_json   TEXT,
    log_text      TEXT
);

CREATE TABLE IF NOT EXISTS google_token (
    user_id       TEXT PRIMARY KEY REFERENCES "user"(user_id),
    access_token  TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    scope         TEXT,
    email         TEXT,
    connected_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_oauth_state (
    state         TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES "user"(user_id),
    code_verifier TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batch (
    batch_id      TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES "user"(user_id),
    name          TEXT,
    config_ref    TEXT NOT NULL,
    source_refs   TEXT NOT NULL,
    target_json   TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',
    results_json  TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_project_user ON project(user_id);
CREATE INDEX IF NOT EXISTS ix_run_user ON run(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_run_project ON run(project_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_batch_user ON batch(user_id, created_at DESC);
"""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _load_env() -> None:
    """Read .env so PG* variables are available without exporting them."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class _Connection:
    """Thin wrapper so connect() works as a context manager for safe cleanup."""

    def __init__(self, con: psycopg.Connection):
        self._con = con

    def execute(self, *args, **kwargs):
        return self._con.execute(*args, **kwargs)

    def commit(self):
        self._con.commit()

    def close(self):
        self._con.close()

    def __enter__(self):
        return self._con.__enter__()

    def __exit__(self, *args):
        return self._con.__exit__(*args)


def connect() -> _Connection:
    _load_env()
    url = os.environ.get("DATABASE_URL")
    if url:
        con = psycopg.connect(url, row_factory=dict_row)
    else:
        con = psycopg.connect(
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
            dbname=os.environ.get("PGDATABASE", "excel_parser"),
            user=os.environ.get("PGUSER", ""),
            password=os.environ.get("PGPASSWORD", ""),
            row_factory=dict_row,
        )
    schema = APP_SCHEMA
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    con.execute(f'SET search_path TO "{schema}"')
    con.commit()
    return _Connection(con)


def init() -> None:
    con = connect()
    con.execute(SCHEMA)
    con.commit()
    con.close()


def dumps(value) -> str:
    return json.dumps(value, default=str)


def loads(text, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default
