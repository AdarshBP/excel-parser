"""Batch processing: validate and push multiple source files against one config.

Every file is validated independently. Push only proceeds when ALL files pass.
Each file gets its own file_id and transaction; a failure stops the batch.
"""
import hashlib
from pathlib import Path

from fastapi import HTTPException

import engine
import sources
import state


def resolve_config(config_ref: str, user_id: str) -> Path:
    try:
        return sources.resolve(config_ref, "config", user_id)
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _csv_source_name(source: Path, source_ref: str, source_path: Path = None) -> str | None:
    """Original filename stem for CSV files so the adapter uses the right sheet name.

    When a CSV is uploaded, the on-disk name is a content-addressed hash or a
    temp-dir prefix. This returns the original stem so ``sheet_config.sheet_name``
    can match.
    """
    if source.suffix.lower() != ".csv":
        return None
    if source_path is not None:
        # Direct upload: source_ref is the original filename
        return Path(source_ref).stem
    if sources.looks_like_upload(source_ref):
        return Path(sources.upload_original_name(source_ref)).stem
    return None


def validate_file(config: Path, source_ref: str, user_id: str,
                  overrides: dict, target_schema: str = None,
                  source_path: Path = None) -> dict:
    """Validate one source file against the config. Returns a per-file result dict.

    If `source_path` is given, it is used directly (for uploaded files that are
    already on disk in a temp directory). Otherwise `source_ref` is resolved
    through `sources.resolve()`.
    """
    name = source_ref.split("/")[-1].split("?")[0]
    try:
        source = source_path or sources.resolve(source_ref, "source", user_id)
        name = source.name
    except sources.SourceError as exc:
        return {"ref": source_ref, "name": name, "status": "error",
                "message": str(exc), "issues": [], "rows": 0, "tables": 0}

    sname = _csv_source_name(source, source_ref, source_path)

    try:
        issues = engine.validator.validate(
            config, source, overrides.get("prefix"), overrides.get("target"),
            overrides.get("database"), overrides.get("id_type"),
            source_name=sname)
    except SystemExit as exc:
        return {"ref": source_ref, "name": name, "status": "error",
                "message": str(exc), "issues": [], "rows": 0, "tables": 0}

    errors = [{"severity": i.severity, "where": i.where, "message": i.message}
              for i in issues if i.severity == "error"]
    warnings = [{"severity": i.severity, "where": i.where, "message": i.message}
                for i in issues if i.severity == "warning"]

    # Check for data quality issues (strict mode)
    bad_cells, skipped = 0, 0
    try:
        previews = engine.preview.previews(config, source, limit=0,
                                           source_name=sname)
        for p in previews.values():
            bad_cells += len(p.get("bad_cells", []))
            skipped += len(p.get("skipped", []))
    except Exception:
        pass

    # Check for duplicate (already loaded into the database)
    sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    duplicate = False
    try:
        where = engine.validator.resolve_target(
            config, overrides.get("target"), overrides.get("database"),
            overrides.get("prefix"), overrides.get("id_type"))
        engine.dbmod.load_env(state.PROJECT_ROOT / ".env")
        con = engine.dbmod.connect(where.target, where.database,
                                   where.prefix, where.db_schema)
        try:
            if where.target == "postgres":
                with con.con.cursor() as cur:
                    cur.execute(
                        f"SELECT 1 FROM {where.prefix}load_config_audit "
                        "WHERE file_sha256 = %s LIMIT 1", (sha256,))
                    duplicate = cur.fetchone() is not None
            else:
                row = con.con.execute(
                    f"SELECT 1 FROM {where.prefix}load_config_audit "
                    "WHERE file_sha256 = ? LIMIT 1", (sha256,)).fetchone()
                duplicate = row is not None
        except Exception:
            pass
        con.close()
    except Exception:
        pass

    if duplicate:
        return {"ref": source_ref, "name": name, "status": "error",
                "message": "Already loaded — this file has identical content to a previous push",
                "issues": [], "rows": 0, "tables": 0,
                "bad_cells": 0, "skipped": 0, "sha256": sha256}

    # Count expected rows
    rows, tables = 0, 0
    try:
        previews = engine.preview.previews(config, source, limit=0,
                                           source_name=sname)
        for p in previews.values():
            rows += p.get("loadable_rows", 0)
            tables += 1
    except Exception:
        pass

    if errors:
        return {"ref": source_ref, "name": name, "status": "error",
                "message": f"{len(errors)} validation error(s)",
                "issues": errors + warnings, "rows": rows, "tables": tables,
                "bad_cells": bad_cells, "skipped": skipped, "sha256": sha256}

    # bad_cells (type mismatches in required columns) block the push.
    # skipped rows and empty sections are normal — they become warnings.
    if bad_cells:
        return {"ref": source_ref, "name": name, "status": "error",
                "message": f"{bad_cells} value(s) don't match their column type",
                "issues": errors + warnings, "rows": rows, "tables": tables,
                "bad_cells": bad_cells, "skipped": skipped, "sha256": sha256}

    message = f"{tables} tables, {rows} rows"
    if skipped:
        message += f" ({skipped} empty row(s) skipped)"
    return {"ref": source_ref, "name": name, "status": "valid",
            "message": message,
            "issues": warnings, "rows": rows, "tables": tables,
            "bad_cells": 0, "skipped": skipped, "sha256": sha256}


def validate_batch(config_ref: str, source_refs: list, user_id: str,
                   overrides: dict) -> list:
    """Validate all source files. Returns a list of per-file results."""
    config = resolve_config(config_ref, user_id)
    target_schema = overrides.get("db_schema")

    # Check for duplicates within the list
    seen = {}
    results = []
    for ref in source_refs:
        ref = ref.strip()
        if ref in seen:
            results.append({"ref": ref, "name": ref.split("/")[-1], "status": "error",
                            "message": "duplicate — this file is already in the list",
                            "issues": [], "rows": 0, "tables": 0,
                            "bad_cells": 0, "skipped": 0, "sha256": ""})
            continue
        seen[ref] = True
        result = validate_file(config, ref, user_id, overrides, target_schema)

        # Check for SHA duplicate within this batch
        if result["status"] == "valid" and result.get("sha256"):
            for prev in results:
                if prev.get("sha256") == result["sha256"] and prev["status"] == "valid":
                    result["status"] = "error"
                    result["message"] = f"duplicate content — identical to {prev['name']}"
                    break
        results.append(result)

    return results


def push_batch(config_ref: str, source_refs: list, user_id: str,
               overrides: dict) -> dict:
    """Push all source files. All must be valid first."""
    config = resolve_config(config_ref, user_id)

    # Build the DDL and ensure schema on first push
    where = engine.validator.resolve_target(
        config, overrides.get("target"), overrides.get("database"),
        overrides.get("prefix"), overrides.get("id_type"))
    sheets, columns = engine.validator.read_config(config)
    dialect = where.target
    schema_sql = engine.validator.render_ddl(sheets, columns, dialect, where.prefix,
                                             where.id_type)

    if where.target == "sqlite":
        from service import sqlite_path
        database = sqlite_path(where.database)
    else:
        database = overrides.get("database") or where.database

    file_results = []
    total_rows = 0
    for ref in source_refs:
        ref = ref.strip()
        source = sources.resolve(ref, "source", user_id)
        sname = _csv_source_name(source, ref)
        lines = []
        try:
            result = engine.executor.execute(
                config, source, where.target, database, where.prefix,
                schema_sql, 0, lines.append, where.id_type, strict=True,
                source_ref=ref, config_ref=config_ref,
                source_name=sname)
            file_results.append({
                "ref": ref, "name": source.name, "status": "pushed",
                "file_id": result.file_id, "rows": result.total,
                "per_table": result.per_table,
            })
            total_rows += result.total
        except SystemExit as exc:
            file_results.append({
                "ref": ref, "name": source.name, "status": "failed",
                "message": str(exc), "rows": 0,
            })
            # Stop the batch on first failure
            for remaining in source_refs[source_refs.index(ref) + 1:]:
                file_results.append({
                    "ref": remaining.strip(), "name": remaining.strip().split("/")[-1],
                    "status": "skipped", "message": "batch stopped due to earlier failure",
                    "rows": 0,
                })
            break
        except Exception as exc:
            file_results.append({
                "ref": ref, "name": source.name, "status": "failed",
                "message": str(exc), "rows": 0,
            })
            break

    pushed = sum(1 for f in file_results if f["status"] == "pushed")
    failed = sum(1 for f in file_results if f["status"] == "failed")
    return {
        "files": file_results, "total_rows": total_rows,
        "pushed": pushed, "failed": failed, "total": len(source_refs),
        "target": {"target": where.target, "database": database or "",
                   "db_schema": where.db_schema or "", "prefix": where.prefix or ""},
    }
