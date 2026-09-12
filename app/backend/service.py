"""Validate, render and push - the parser driven on behalf of one project.

Everything the API needs from the parser lives here, and every parser call is
wrapped by `guard()`: the CLI raises SystemExit for a bad workbook, which must
become a 400 for the user rather than a dead worker.
"""
import os
from pathlib import Path

from fastapi import HTTPException

import engine
import sources
import state

PREVIEW_LIMIT = 20
MAX_PREVIEW_LIMIT = 200


def _display_name(path: Path, ref: str) -> str:
    """The user-facing name: original filename for upload refs, path.name otherwise."""
    if sources.looks_like_upload(ref):
        return sources.upload_original_name(ref)
    return path.name


def _csv_source_name(path: Path, ref: str) -> str | None:
    """Original filename stem for uploaded CSV files, so the CSV adapter uses
    the right sheet name instead of the content-addressed hash.

    Returns None for non-CSV or non-upload refs (the adapter falls back to
    path.stem, which is already correct in those cases).
    """
    if path.suffix.lower() != ".csv":
        return None
    if not sources.looks_like_upload(ref):
        return None
    original = sources.upload_original_name(ref)
    return Path(original).stem


DATA_DIR = state.APP_DIR / "data"


def guard(what: str, call, *args, **kwargs):
    """Run a parser call; turn its own error text into a 400."""
    try:
        return call(*args, **kwargs)
    except SystemExit as exc:
        raise HTTPException(status_code=400, detail=f"{what}: {exc}") from exc
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:                       # openpyxl & friends
        raise HTTPException(status_code=400,
                            detail=f"{what}: {exc}") from exc


def sqlite_path(database) -> str:
    """SQLite files live under app/data, whatever the workbook wrote."""
    name = Path(str(database or "excel_parser.db")).name
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(DATA_DIR / name)


def resolve_pair(project) -> tuple:
    """(config path, source path) for a project, fetching from Google if needed.

    Drive references are read with the project owner's own read-only token, so a
    file nobody shared with him stays unreadable here too.
    """
    owner = project["user_id"]
    config = guard("configuration", sources.resolve, project["config_ref"], "config", owner)
    source = guard("source", sources.resolve, project["source_ref"], "source", owner)
    return config, source


def target_of(config: Path, overrides: dict = None) -> dict:
    """Where a push would go. Host comes from the environment, never a password."""
    overrides = overrides or {}
    engine.dbmod.load_env(state.PROJECT_ROOT / ".env")
    where = guard("target_config", engine.validator.resolve_target, config,
                  overrides.get("target"), overrides.get("database"),
                  overrides.get("prefix"), overrides.get("id_type"))
    if where.target == "sqlite":
        database, host = sqlite_path(where.database), "(local file)"
    else:
        database = where.database or os.environ.get("PGDATABASE") or ""
        host = os.environ.get("PGHOST") or ("(DATABASE_URL)"
                                            if os.environ.get("DATABASE_URL") else "")
    return {"target": where.target, "host": host, "database": database,
            "db_schema": where.db_schema or "", "prefix": where.prefix or "",
            "id_type": where.id_type,
            "credentials": "from the server environment/.env"}


def issues_of(config: Path, source: Path, overrides: dict = None,
              source_name: str = None) -> list:
    overrides = overrides or {}
    found = guard("validation", engine.validator.validate, config, source,
                  overrides.get("prefix"), overrides.get("target"),
                  overrides.get("database"), overrides.get("id_type"),
                  source_name=source_name)
    return [{"severity": i.severity, "where": i.where, "message": i.message} for i in found]


def render(project, limit: int = PREVIEW_LIMIT) -> dict:
    """Model + issues + previews for the current content of both workbooks."""
    config, source = resolve_pair(project)
    overrides = state.loads(project["target_json"], {}) or {}
    sname = _csv_source_name(source, project.get("source_ref", ""))
    issues = issues_of(config, source, overrides, source_name=sname)
    errors = [i for i in issues if i["severity"] == "error"]
    prefix, id_type = overrides.get("prefix"), overrides.get("id_type")
    tables = guard("configuration", engine.preview.model, config, prefix, id_type)
    control = guard("configuration", engine.preview.control, config, prefix, id_type)
    previews = {} if errors else guard("preview", engine.preview.previews, config,
                                       source, min(limit, MAX_PREVIEW_LIMIT),
                                       source_name=sname)
    return {
        "tables": tables,
        "control_tables": control,
        "issues": issues,
        "previews": previews,
        "target": target_of(config, overrides),
        "source": {"name": _display_name(source, project["source_ref"]),
                   "ref": project["source_ref"]},
        "config": {"name": _display_name(config, project["config_ref"]),
                   "ref": project["config_ref"]},
        "can_push": not errors,
        "rendered_at": state.now(),
        "preview_limit": min(limit, MAX_PREVIEW_LIMIT),
    }


def ddl(project, dialect: str = None) -> str:
    config, _ = resolve_pair(project)
    overrides = state.loads(project["target_json"], {}) or {}
    where = guard("target_config", engine.validator.resolve_target, config,
                  overrides.get("target"), overrides.get("database"),
                  overrides.get("prefix"), overrides.get("id_type"))
    dialect = (dialect or where.target).lower()
    if dialect not in ("sqlite", "postgres"):
        raise HTTPException(status_code=400, detail="dialect must be sqlite or postgres")
    sheets, columns = guard("configuration", engine.validator.read_config, config)
    return guard("ddl", engine.validator.render_ddl, sheets, columns, dialect, where.prefix,
                 where.id_type)


def push_schema(project) -> dict:
    """Apply only the DDL (CREATE TABLE) without inserting any data."""
    config, _ = resolve_pair(project)
    overrides = state.loads(project["target_json"], {}) or {}
    where = target_of(config, overrides)
    sheets, columns = guard("configuration", engine.validator.read_config, config)
    schema_sql = ddl(project, where["target"])
    database = where["database"] if where["target"] == "sqlite" else overrides.get("database")

    engine.dbmod.load_env(state.PROJECT_ROOT / ".env")
    con = guard("schema", engine.dbmod.connect, where["target"], database,
                overrides.get("prefix") or "", where.get("db_schema"))

    # Check which tables already exist
    prefix = overrides.get("prefix") or ""
    wanted = [engine.dbmod.ident(f"{prefix}{str(s['table_name']).strip()}", "table_name")
              for s in sheets] + [f"{prefix}load_config_audit"]
    already = [t for t in wanted if t not in con.missing_tables(wanted)]
    missing = con.missing_tables(wanted)

    if already and not missing:
        con.close()
        return {"target": where, "target_label": f"{con.name} {con.label}",
                "created": False, "tables_existed": already,
                "message": f"All {len(already)} table(s) already exist — nothing to create"}

    try:
        con.ensure_schema(schema_sql)
        con.commit()
    except Exception as exc:
        con.close()
        raise HTTPException(status_code=400,
                            detail=f"schema creation failed: {exc}") from exc
    label = f"{con.name} {con.label}"
    con.close()
    return {"target": where, "target_label": label, "created": True,
            "tables_existed": already, "tables_created": missing,
            "message": f"{len(missing)} table(s) created in {label}"}


def push(project) -> dict:
    """Validate, apply the DDL if needed, and insert. Nothing on any error."""
    config, source = resolve_pair(project)
    overrides = state.loads(project["target_json"], {}) or {}
    where = target_of(config, overrides)
    sname = _csv_source_name(source, project.get("source_ref", ""))

    issues = issues_of(config, source, overrides, source_name=sname)
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        raise HTTPException(status_code=400, detail={
            "message": f"{len(errors)} validation error(s) - nothing was pushed",
            "issues": errors[:20]})

    lines = []
    schema_sql = ddl(project, where["target"])
    database = where["database"] if where["target"] == "sqlite" else overrides.get("database")
    source_ref = project.get("source_ref") or None
    config_ref = project.get("config_ref") or None
    skip_audit = project.get("skip_audit", False)
    result = guard("push", engine.executor.execute, config, source, where["target"],
                   database, overrides.get("prefix"), schema_sql, 0, lines.append,
                   overrides.get("id_type"), strict=True,
                   source_ref=source_ref, config_ref=config_ref,
                   skip_audit=skip_audit, source_name=sname)
    return {
        "file_id": result.file_id, "row_total": result.total,
        "rows_per_table": result.per_table, "skipped_rows": result.skipped_rows,
        "bad_cells": result.bad_cells, "target_label": result.target,
        "target": where, "issues": issues, "log": lines,
        "source_name": _display_name(source, project.get("source_ref", "")),
        "config_name": _display_name(config, project.get("config_ref", "")),
    }


def fingerprints(project) -> dict:
    owner = project["user_id"]
    return {
        "source": guard("source", sources.fingerprint, project["source_ref"], "source", owner),
        "config": guard("configuration", sources.fingerprint, project["config_ref"],
                        "config", owner),
    }
