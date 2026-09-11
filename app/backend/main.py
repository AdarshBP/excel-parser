"""Excel Parser - HTTP API.

Every endpoint except /api/auth/login and /api/health requires a session, and
every project and run is filtered by the caller's user_id, so one user never
sees another's work. The parser itself is imported unchanged from tools/.

    uvicorn main:app --port 8000            (run.sh does this for you)
"""
import logging
import os
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

log = logging.getLogger("excel_parser")

import auth
import batch as batchmod
import drive
import service
import sources
import state

ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "APP_ALLOWED_ORIGINS", "http://localhost:4200").split(",") if o.strip()]

app = FastAPI(title="Excel Parser", version="1.0.0", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["content-type", auth.CSRF_HEADER])


@app.exception_handler(psycopg.Error)
async def db_error(request: Request, exc: psycopg.Error):
    log.error("database error: %s", exc)
    return JSONResponse(status_code=503,
                        content={"detail": "the database is temporarily unavailable"})


@app.exception_handler(Exception)
async def fallback_error(request: Request, exc: Exception):
    log.error("unhandled error on %s %s: %s", request.method, request.url.path, exc,
              exc_info=True)
    return JSONResponse(status_code=500,
                        content={"detail": "an internal error occurred"})


@app.on_event("startup")
def startup() -> None:
    state.init()
    service.engine.dbmod.load_env(state.PROJECT_ROOT / ".env")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return response


# ------------------------------------------------------------------ models


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=8, max_length=256)


class TargetOverride(BaseModel):
    target: str | None = Field(default=None, pattern="^(sqlite|postgres)$")
    database: str | None = Field(default=None, max_length=200)
    prefix: str | None = Field(default=None, max_length=40)
    id_type: str | None = Field(default=None, pattern="^(integer|uuid)$")


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_ref: str = Field(min_length=1, max_length=2000)
    config_ref: str = Field(min_length=1, max_length=2000)
    target: TargetOverride | None = None
    auto_render: bool = False


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_ref: str | None = Field(default=None, min_length=1, max_length=2000)
    config_ref: str | None = Field(default=None, min_length=1, max_length=2000)
    target: TargetOverride | None = None
    auto_render: bool | None = None


# ------------------------------------------------------------------ helpers


def csrf(request: Request) -> None:
    auth.check_csrf(request)


def project_row(project_id: str, user: dict):
    """One project, or 404 - a project of another user does not exist here."""
    con = state.connect()
    row = con.execute("SELECT * FROM project WHERE project_id = %s AND user_id = %s",
                      (project_id, user["user_id"])).fetchone()
    con.close()
    if row is None:
        raise HTTPException(status_code=404, detail="no such project")
    return row


def as_project(row) -> dict:
    return {
        "project_id": row["project_id"], "name": row["name"],
        "source_ref": row["source_ref"], "config_ref": row["config_ref"],
        "source_kind": sources.kind_of(row["source_ref"]),
        "config_kind": sources.kind_of(row["config_ref"]),
        "target": state.loads(row["target_json"], {}) or {},
        "auto_render": bool(row["auto_render"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "last_render_at": row["last_render_at"], "last_push_at": row["last_push_at"],
    }


# ------------------------------------------------------------------- auth


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/template")
def download_template():
    """Download the configuration template workbook."""
    template = state.PROJECT_ROOT / "template" / "config_template.xlsx"
    if not template.is_file():
        raise HTTPException(status_code=404, detail="template file not found")
    from fastapi.responses import FileResponse
    return FileResponse(template, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename="config_template.xlsx")


@app.post("/api/auth/login")
def do_login(body: Credentials, response: Response) -> dict:
    return auth.login(body.username, body.password, response)


@app.post("/api/auth/logout")
def do_logout(request: Request, response: Response) -> dict:
    auth.logout(request, response)
    return {"status": "logged out"}


@app.get("/api/auth/me")
def me(user: dict = auth.Me) -> dict:
    return {"username": user["username"],
            "must_change_password": user["must_change_password"]}


@app.post("/api/auth/password")
def password(body: PasswordChange, user: dict = auth.Me,
             _: None = Depends(csrf)) -> dict:
    auth.change_password(user, body.current, body.new)
    return {"status": "password changed"}


# --------------------------------------------------------------- projects


@app.get("/api/projects")
def list_projects(user: dict = auth.Me, limit: int = Query(100, ge=1, le=200)) -> list:
    con = state.connect()
    rows = con.execute("SELECT * FROM project WHERE user_id = %s "
                       "ORDER BY updated_at DESC LIMIT %s",
                       (user["user_id"], limit)).fetchall()
    con.close()
    return [as_project(r) for r in rows]


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectIn, user: dict = auth.Me,
                   _: None = Depends(csrf)) -> dict:
    for label, ref in (("source", body.source_ref), ("config", body.config_ref)):
        # fail fast with the reason, rather than saving a project that cannot render
        service.guard(label, sources.resolve, ref, label, user["user_id"])
    project_id = state.new_id()
    con = state.connect()
    with con:
        con.execute(
            "INSERT INTO project (project_id, user_id, name, source_ref, config_ref, "
            "target_json, auto_render, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (project_id, user["user_id"], body.name.strip(), body.source_ref.strip(),
             body.config_ref.strip(),
             state.dumps(body.target.model_dump(exclude_none=True) if body.target else {}),
             int(body.auto_render), state.now(), state.now()))
    con.close()
    return as_project(project_row(project_id, user))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, user: dict = auth.Me) -> dict:
    row = project_row(project_id, user)
    out = as_project(row)
    out["render"] = state.loads(row["render_json"])
    out["fingerprints"] = {"source": row["source_sha256"], "config": row["config_sha256"]}
    return out


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch, user: dict = auth.Me,
                  _: None = Depends(csrf)) -> dict:
    row = project_row(project_id, user)
    fields, values = [], []
    for column, value in (("name", body.name), ("source_ref", body.source_ref),
                          ("config_ref", body.config_ref)):
        if value is not None:
            fields.append(f"{column} = %s")
            values.append(value.strip())
    if body.target is not None:
        fields.append("target_json = %s")
        values.append(state.dumps(body.target.model_dump(exclude_none=True)))
    if body.auto_render is not None:
        fields.append("auto_render = %s")
        values.append(int(body.auto_render))
    if not fields:
        return as_project(row)
    fields.append("updated_at = %s")
    values += [state.now(), project_id, user["user_id"]]
    con = state.connect()
    with con:
        con.execute(f"UPDATE project SET {', '.join(fields)} "        # fixed column names
                    "WHERE project_id = %s AND user_id = %s", values)
    con.close()
    return as_project(project_row(project_id, user))


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user: dict = auth.Me,
                   _: None = Depends(csrf)) -> dict:
    project_row(project_id, user)
    con = state.connect()
    with con:
        con.execute("DELETE FROM run WHERE project_id = %s AND user_id = %s",
                    (project_id, user["user_id"]))
        con.execute("DELETE FROM project WHERE project_id = %s AND user_id = %s",
                    (project_id, user["user_id"]))
    con.close()
    return {"status": "deleted"}


@app.post("/api/projects/{project_id}/duplicate", status_code=201)
def duplicate_project(project_id: str, user: dict = auth.Me,
                      _: None = Depends(csrf)) -> dict:
    row = project_row(project_id, user)
    new = state.new_id()
    con = state.connect()
    with con:
        con.execute(
            "INSERT INTO project (project_id, user_id, name, source_ref, config_ref, "
            "target_json, auto_render, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (new, user["user_id"], f"{row['name']} (copy)", row["source_ref"],
             row["config_ref"], row["target_json"], row["auto_render"],
             state.now(), state.now()))
    con.close()
    return as_project(project_row(new, user))


# -------------------------------------------------------- render and push


@app.post("/api/projects/{project_id}/render")
def render(project_id: str, user: dict = auth.Me,
           limit: int = Query(service.PREVIEW_LIMIT, ge=1, le=service.MAX_PREVIEW_LIMIT),
           _: None = Depends(csrf)) -> dict:
    row = project_row(project_id, user)
    result = service.render(row, limit)
    marks = service.fingerprints(row)
    con = state.connect()
    with con:
        con.execute("UPDATE project SET last_render_at = %s, render_json = %s, "
                    "source_sha256 = %s, config_sha256 = %s WHERE project_id = %s",
                    (state.now(), state.dumps(result), marks["source"]["sha256"],
                     marks["config"]["sha256"], project_id))
    con.close()
    return result


@app.get("/api/projects/{project_id}/status")
def status(project_id: str, user: dict = auth.Me) -> dict:
    """The 5-second poll: has either workbook changed since the last render?"""
    row = project_row(project_id, user)
    marks = service.fingerprints(row)
    return {
        "source_changed": bool(row["source_sha256"]
                               and row["source_sha256"] != marks["source"]["sha256"]),
        "config_changed": bool(row["config_sha256"]
                               and row["config_sha256"] != marks["config"]["sha256"]),
        "never_rendered": row["last_render_at"] is None,
        "source": {k: marks["source"][k] for k in ("name", "sha256", "size")},
        "config": {k: marks["config"][k] for k in ("name", "sha256", "size")},
        "last_render_at": row["last_render_at"], "last_push_at": row["last_push_at"],
        "auto_render": bool(row["auto_render"]),
        "checked_at": state.now(),
    }


@app.get("/api/projects/{project_id}/target")
def target(project_id: str, user: dict = auth.Me) -> dict:
    row = project_row(project_id, user)
    config, _ = service.resolve_pair(row)
    return service.target_of(config, state.loads(row["target_json"], {}) or {})


@app.get("/api/projects/{project_id}/ddl", response_class=PlainTextResponse)
def ddl(project_id: str, user: dict = auth.Me, dialect: str | None = None) -> str:
    row = project_row(project_id, user)
    return service.ddl(row, dialect)


@app.get("/api/projects/{project_id}/export-csv")
def export_csv(project_id: str, table: str = Query(...), user: dict = auth.Me):
    """Export a rendered preview table as CSV."""
    import csv
    import io
    row = project_row(project_id, user)
    result = service.render(row, limit=100000)
    preview = result["previews"].get(table)
    if not preview:
        raise HTTPException(status_code=404, detail=f"table '{table}' not found in render")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(preview["columns"])
    for r in preview["rows"]:
        writer.writerow([c["value"] for c in r["cells"]])
    buf.seek(0)
    filename = f"{table}.csv"
    return StreamingResponse(buf, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/projects/{project_id}/push-schema")
def push_schema(project_id: str, user: dict = auth.Me, _: None = Depends(csrf)) -> dict:
    """Apply the DDL (create tables) without inserting data."""
    row = project_row(project_id, user)
    return service.push_schema(row)


@app.post("/api/projects/{project_id}/push")
def push(project_id: str, skip_audit: bool = Query(False),
         user: dict = auth.Me, _: None = Depends(csrf)) -> dict:
    row = project_row(project_id, user)
    row = dict(row)
    row["skip_audit"] = skip_audit
    run_id = state.new_id()
    marks = service.fingerprints(row)
    con = state.connect()
    with con:
        con.execute("INSERT INTO run (run_id, project_id, user_id, started_at, status, "
                    "source_sha256, config_sha256) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (run_id, project_id, user["user_id"], state.now(), "running",
                     marks["source"]["sha256"], marks["config"]["sha256"]))
    con.close()

    try:
        result = service.push(row)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            detail = exc.detail
            message = detail.get("message") if isinstance(detail, dict) else str(detail)
            issues = detail.get("issues") if isinstance(detail, dict) else []
        else:
            log.error("push failed for run %s: %s", run_id, exc, exc_info=True)
            message = "an internal error occurred during the push"
            issues = []
        try:
            con = state.connect()
            with con:
                con.execute("UPDATE run SET finished_at = %s, status = %s, log_text = %s, "
                            "issues_json = %s WHERE run_id = %s",
                            (state.now(), "failed", message, state.dumps(issues), run_id))
            con.close()
        except Exception:
            log.error("could not mark run %s as failed", run_id, exc_info=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=message) from exc

    where = result["target"]
    con = state.connect()
    with con:
        con.execute(
            "UPDATE run SET finished_at = %s, status = %s, target = %s, database = %s, "
            "db_schema = %s, prefix = %s, file_id = %s, row_total = %s, source_name = %s, "
            "config_name = %s, rows_json = %s, issues_json = %s, log_text = %s "
            "WHERE run_id = %s",
            (state.now(), "succeeded", where["target"], where["database"],
             where["db_schema"], where["prefix"], result["file_id"], result["row_total"],
             result["source_name"], result["config_name"],
             state.dumps(result["rows_per_table"]), state.dumps(result["issues"]),
             "\n".join(result["log"]), run_id))
        con.execute("UPDATE project SET last_push_at = %s WHERE project_id = %s",
                    (state.now(), project_id))
    con.close()
    return {"run_id": run_id, **result}


# ------------------------------------------------------------------- runs


@app.get("/api/runs")
def list_runs(user: dict = auth.Me, project_id: str | None = None,
              limit: int = Query(50, ge=1, le=200)) -> list:
    con = state.connect()

    # 1) Project pushes from the run table
    sql = ("SELECT r.*, p.name AS project_name FROM run r "
           "JOIN project p ON p.project_id = r.project_id WHERE r.user_id = %s")
    params: list = [user["user_id"]]
    if project_id:
        sql += " AND r.project_id = %s"
        params.append(project_id)
    sql += " ORDER BY r.started_at DESC LIMIT %s"
    params.append(limit)
    rows = con.execute(sql, params).fetchall()

    items = [{
        "run_id": r["run_id"], "project_id": r["project_id"],
        "project_name": r["project_name"], "started_at": r["started_at"],
        "finished_at": r["finished_at"], "status": r["status"], "target": r["target"],
        "database": r["database"], "db_schema": r["db_schema"], "prefix": r["prefix"],
        "row_total": r["row_total"], "file_id": r["file_id"],
        "source_name": r["source_name"], "config_name": r["config_name"],
        "origin": "project",
    } for r in rows]

    # 2) Batch pushes — expand individual files from completed batches
    if not project_id:
        batch_rows = con.execute(
            "SELECT batch_id, config_ref, target_json, results_json, created_at "
            "FROM batch WHERE user_id = %s AND status IN ('done', 'partial') "
            "ORDER BY created_at DESC", (user["user_id"],)).fetchall()
        for b in batch_rows:
            result = state.loads(b["results_json"], {})
            target = result.get("target", state.loads(b["target_json"], {}))
            for idx, f in enumerate(result.get("files", [])):
                pushed = f.get("status") == "pushed"
                items.append({
                    "run_id": f"{b['batch_id']}:{idx}",
                    "project_id": None,
                    "project_name": None,
                    "started_at": b["created_at"],
                    "finished_at": b["created_at"],
                    "status": "succeeded" if pushed else "failed",
                    "target": target.get("target"),
                    "database": target.get("database"),
                    "db_schema": target.get("db_schema"),
                    "prefix": target.get("prefix"),
                    "row_total": f.get("rows", 0),
                    "file_id": f.get("file_id") if pushed else None,
                    "source_name": f.get("name", ""),
                    "config_name": b["config_ref"],
                    "origin": "batch",
                })

    con.close()
    items.sort(key=lambda x: x["started_at"] or "", reverse=True)
    return items[:limit]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, user: dict = auth.Me) -> dict:
    con = state.connect()
    row = con.execute("SELECT r.*, p.name AS project_name, p.source_ref, p.config_ref "
                      "FROM run r JOIN project p ON p.project_id = r.project_id "
                      "WHERE r.run_id = %s AND r.user_id = %s",
                      (run_id, user["user_id"])).fetchone()
    con.close()
    if row is None:
        raise HTTPException(status_code=404, detail="no such run")
    out = {k: row[k] for k in row.keys() if k not in ("rows_json", "issues_json")}
    out["rows_per_table"] = state.loads(row["rows_json"], {})
    out["issues"] = state.loads(row["issues_json"], [])
    return out


# -------------------------------------------------------------- data viewer


def _scan_audit_tables() -> list:
    """Find all load_config_audit tables across every schema in the target DB.

    Returns a flat list of file records, one per (file_id, schema) combination,
    with per-table details aggregated. Works regardless of how the push happened
    (project, batch, one-off upload).

    Reuses state.connect() so it works in every environment (local, Docker,
    production) without duplicating connection logic.
    """
    con = state.connect()

    # Find every *load_config_audit table across all schemas
    # (state.connect sets search_path to APP_SCHEMA, but information_schema
    # queries work regardless of search_path)
    audit_tables = con.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_name LIKE '%%load_config_audit' "
        "AND table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast', %s)",
        (state.APP_SCHEMA,)).fetchall()

    files: dict = {}   # file_id -> record
    for at in audit_tables:
        schema = at["table_schema"]
        table = at["table_name"]
        qualified = f'"{schema}"."{table}"'
        try:
            rows = con.execute(
                f"SELECT file_id, file_name, file_sha256, source_ref, config_ref, "
                f"table_name, sheet_name, header_row, data_start_row, data_end_row, "
                f"column_count, row_count, loaded_at "
                f"FROM {qualified} ORDER BY loaded_at DESC"
            ).fetchall()
        except Exception as exc:
            log.warning("could not read %s: %s", qualified, exc)
            continue

        for r in rows:
            fid = r["file_id"]
            tbl = {
                "table_name": r["table_name"], "sheet_name": r["sheet_name"],
                "header_row": r["header_row"], "data_start_row": r["data_start_row"],
                "data_end_row": r["data_end_row"], "column_count": r["column_count"],
                "row_count": r["row_count"],
                "loaded_at": str(r["loaded_at"]) if r["loaded_at"] else None,
                "file_sha256": r["file_sha256"],
            }
            if fid not in files:
                files[fid] = {
                    "file_id": fid,
                    "source_name": r["file_name"],
                    "file_sha256": r["file_sha256"],
                    "source_ref": r["source_ref"],
                    "config_ref": r["config_ref"],
                    "db_schema": schema if schema != "public" else "",
                    "pushed_at": str(r["loaded_at"]) if r["loaded_at"] else None,
                    "row_total": 0,
                    "tables": [],
                    "rows_per_table": {},
                }
            files[fid]["tables"].append(tbl)
            files[fid]["row_total"] += r["row_count"] or 0
            files[fid]["rows_per_table"][r["table_name"]] = r["row_count"] or 0
            # Keep the earliest loaded_at as the push time
            if r["loaded_at"]:
                ts = str(r["loaded_at"])
                existing = files[fid]["pushed_at"]
                if not existing or ts < existing:
                    files[fid]["pushed_at"] = ts

    con.close()
    return sorted(files.values(), key=lambda f: f.get("pushed_at") or "", reverse=True)


@app.get("/api/data-viewer/files")
def data_viewer_files(user: dict = auth.Me,
                      search: str = Query("", max_length=200),
                      limit: int = Query(100, ge=1, le=500)) -> list:
    """List all pushed files from load_config_audit in the target database.

    This is the single source of truth — works for project pushes, batch pushes,
    and one-off uploads alike.
    """
    all_files = _scan_audit_tables()
    q = search.strip().lower()
    if q:
        all_files = [f for f in all_files
                     if q in (f.get("source_name") or "").lower()
                     or q in (f.get("config_ref") or "").lower()
                     or q in (f.get("db_schema") or "").lower()
                     or q in (f.get("file_id") or "").lower()]
    return all_files[:limit]


@app.get("/api/data-viewer/files/{file_id}")
def data_viewer_file_detail(file_id: str, user: dict = auth.Me) -> dict:
    """Detailed metadata for one pushed file from load_config_audit."""
    all_files = _scan_audit_tables()
    for f in all_files:
        if f["file_id"] == file_id:
            return f
    raise HTTPException(status_code=404,
                        detail=f"File not found: no data has been loaded with file_id "
                               f"'{file_id}'. It may have been rolled back or the database "
                               f"was cleared. Refresh the Data Viewer to see current files.")


@app.post("/api/data-viewer/files/{file_id}/rollback")
def data_viewer_rollback(file_id: str, user: dict = auth.Me,
                         _: None = Depends(csrf)) -> dict:
    """Delete all rows loaded by a specific file_id and remove audit records.

    The entire operation runs in one transaction — if any table fails,
    nothing is deleted. The run/batch record in the app schema is updated
    to 'rolled_back' status.
    """
    # Find the file in audit tables to get schema/prefix info
    all_files = _scan_audit_tables()
    target_file = None
    for f in all_files:
        if f["file_id"] == file_id:
            target_file = f
            break
    if target_file is None:
        raise HTTPException(status_code=404,
                            detail=f"Cannot rollback: no data found for file_id '{file_id}'. "
                                   f"The file may have already been rolled back or the "
                                   f"database was cleared.")

    db_schema = target_file.get("db_schema") or None

    try:
        import psycopg
        from psycopg.rows import dict_row as _dr

        # Connect directly to the target schema (not through state.connect()
        # which locks search_path to the app schema)
        state._load_env()
        url = os.environ.get("DATABASE_URL")
        if url:
            con = psycopg.connect(url, row_factory=_dr)
        else:
            con = psycopg.connect(
                host=os.environ.get("PGHOST", "localhost"),
                port=os.environ.get("PGPORT", "5432"),
                dbname=os.environ.get("PGDATABASE", "excel_parser"),
                user=os.environ.get("PGUSER", ""),
                password=os.environ.get("PGPASSWORD", ""),
                row_factory=_dr,
            )
        schema = db_schema or "public"
        con.execute(f'SET search_path TO "{schema}"')

        # Find the audit table name (may have a prefix, e.g. swiggy_load_config_audit)
        audit_table_row = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name LIKE '%%load_config_audit'",
            (schema,)).fetchone()
        if not audit_table_row:
            con.close()
            raise HTTPException(status_code=404,
                                detail=f"No audit table found in schema '{schema}'. "
                                       f"The target schema may have been dropped.")
        audit_table = audit_table_row["table_name"]

        # Find tables from audit
        audit_rows = con.execute(
            f'SELECT table_name FROM "{audit_table}" WHERE file_id = %s',
            (file_id,)).fetchall()
        if not audit_rows:
            con.close()
            raise HTTPException(status_code=404,
                                detail=f"No audit records found for file_id '{file_id}' in "
                                       f"schema '{schema}'. The data may have "
                                       f"already been deleted.")

        # Count rows per table, then delete
        deleted = {}
        total = 0
        for r in audit_rows:
            table = r["table_name"]
            count_row = con.execute(
                f'SELECT count(*) as c FROM "{table}" WHERE file_id = %s',
                (file_id,)).fetchone()
            count = count_row["c"] if count_row else 0
            con.execute(f'DELETE FROM "{table}" WHERE file_id = %s', (file_id,))
            deleted[table] = count
            total += count

        # Delete audit records
        con.execute(f'DELETE FROM "{audit_table}" WHERE file_id = %s', (file_id,))
        con.commit()
        con.close()

        # Update app state: mark run as rolled_back
        app_con = state.connect()
        app_con.execute(
            "UPDATE run SET status = 'rolled_back' WHERE file_id = %s AND user_id = %s",
            (file_id, user["user_id"]))
        app_con.commit()
        app_con.close()

    except HTTPException:
        raise
    except Exception as exc:
        log.error("rollback failed for file %s: %s", file_id, exc, exc_info=True)
        raise HTTPException(status_code=500,
                            detail=f"Rollback failed for '{target_file.get('source_name', file_id)}' "
                                   f"— the operation was aborted and no data was deleted. "
                                   f"Please try again or contact support if the issue persists.") from exc

    return {
        "rolled_back": True, "file_id": file_id,
        "rows_deleted": deleted, "total_deleted": total,
        "source_name": target_file.get("source_name"),
    }


# ----------------------------------------------------------------- batch


class BatchIn(BaseModel):
    config_ref: str = Field(min_length=1, max_length=2000)
    source_refs: list[str] = Field(min_length=1)
    target: TargetOverride | None = None


@app.post("/api/batch/validate")
def batch_validate(body: BatchIn, user: dict = auth.Me,
                   _: None = Depends(csrf)) -> dict:
    """Validate all source files against the config. All must pass before push."""
    overrides = body.target.model_dump(exclude_none=True) if body.target else {}
    results = batchmod.validate_batch(body.config_ref, body.source_refs,
                                      user["user_id"], overrides)
    all_valid = all(r["status"] == "valid" for r in results)
    return {"results": results, "all_valid": all_valid,
            "total": len(results),
            "valid": sum(1 for r in results if r["status"] == "valid"),
            "errors": sum(1 for r in results if r["status"] == "error")}


@app.post("/api/batch/push")
def batch_push(body: BatchIn, user: dict = auth.Me,
               _: None = Depends(csrf)) -> dict:
    """Push all source files. Refuses if any would fail validation."""
    overrides = body.target.model_dump(exclude_none=True) if body.target else {}

    # Re-validate first to ensure nothing changed since the user saw the results
    results = batchmod.validate_batch(body.config_ref, body.source_refs,
                                      user["user_id"], overrides)
    invalid = [r for r in results if r["status"] != "valid"]
    if invalid:
        raise HTTPException(status_code=400, detail={
            "message": f"{len(invalid)} file(s) failed validation — remove them first",
            "files": invalid})

    result = batchmod.push_batch(body.config_ref, body.source_refs,
                                 user["user_id"], overrides)

    # Record in batch table
    batch_id = state.new_id()
    con = state.connect()
    with con:
        con.execute(
            "INSERT INTO batch (batch_id, user_id, config_ref, source_refs, target_json, "
            "status, results_json, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (batch_id, user["user_id"], body.config_ref,
             state.dumps(body.source_refs),
             state.dumps(overrides),
             "done" if result["failed"] == 0 else "partial",
             state.dumps(result), state.now(), state.now()))
    con.close()

    return {"batch_id": batch_id, **result}


MAX_UPLOAD_FILES = 20
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB per file
UPLOAD_SUFFIXES = {".xlsx", ".xlsm", ".csv"}


def _save_uploads(files: list[UploadFile]) -> list[tuple]:
    """Write uploaded files to temp paths; return [(name, Path), ...].

    The files are saved to a temp directory and cleaned up by the caller.
    Nothing is kept on disk after the request completes.
    """
    import shutil
    import tempfile
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400,
                            detail=f"too many files — maximum is {MAX_UPLOAD_FILES}")
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")
    tmp = Path(tempfile.mkdtemp(prefix="ep_upload_"))
    saved = []
    for f in files:
        name = f.filename or "unnamed.xlsx"
        suffix = Path(name).suffix.lower()
        if suffix not in UPLOAD_SUFFIXES:
            shutil.rmtree(tmp, ignore_errors=True)
            raise HTTPException(status_code=400,
                                detail=f"{name}: only .xlsx and .csv files are accepted")
        dest = tmp / f"{len(saved)}_{name}"
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        if dest.stat().st_size > MAX_UPLOAD_BYTES:
            shutil.rmtree(tmp, ignore_errors=True)
            raise HTTPException(status_code=400,
                                detail=f"{name}: file too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")
        saved.append((name, dest))
    return saved, tmp


@app.post("/api/batch/validate-upload")
def batch_validate_upload(request: Request,
                          files: list[UploadFile] = File(...),
                          config_ref: str = Form(...)) -> dict:
    """Validate uploaded source files in-memory. Nothing is saved to disk after the request."""
    user = auth.current_user(request)
    auth.check_csrf(request)
    import shutil
    saved, tmp = _save_uploads(files)
    try:
        config = batchmod.resolve_config(config_ref, user["user_id"])
        results = []
        seen_sha = {}
        for name, path in saved:
            result = batchmod.validate_file(config, name, user["user_id"], {},
                                            target_schema=None, source_path=path)
            result["name"] = name
            result["ref"] = name
            # Check for duplicate content within this batch
            sha = result.get("sha256", "")
            if sha and result["status"] == "valid" and sha in seen_sha:
                result["status"] = "error"
                result["message"] = f"duplicate content — identical to {seen_sha[sha]}"
            elif sha:
                seen_sha[sha] = name
            results.append(result)
        all_valid = all(r["status"] == "valid" for r in results)
        return {"results": results, "all_valid": all_valid,
                "total": len(results),
                "valid": sum(1 for r in results if r["status"] == "valid"),
                "errors": sum(1 for r in results if r["status"] == "error")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/api/batch/validate-one")
def batch_validate_one(request: Request,
                       file: UploadFile = File(...),
                       config_ref: str = Form(...)) -> dict:
    """Validate a single uploaded file. Returns one result dict."""
    user = auth.current_user(request)
    auth.check_csrf(request)
    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="ep_val_"))
    name = file.filename or "unnamed.xlsx"
    suffix = Path(name).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(status_code=400,
                            detail=f"{name}: only .xlsx and .csv files are accepted")
    dest = tmp / name
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    if dest.stat().st_size > MAX_UPLOAD_BYTES:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(status_code=400,
                            detail=f"{name}: file too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")
    try:
        config = batchmod.resolve_config(config_ref, user["user_id"])
        result = batchmod.validate_file(config, name, user["user_id"], {},
                                        target_schema=None, source_path=dest)
        result["name"] = name
        result["ref"] = name
        if result.get("status") != "valid":
            log.info("validate-one %s: %s — %s", name, result.get("status"), result.get("message"))
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _record_batch(user_id: str, config_ref: str, file_results: list,
                   target_info: dict | None = None):
    """Record a batch push (one or more files) in the batch table."""
    batch_id = state.new_id()
    target = target_info or {}
    pushed = sum(1 for f in file_results if f.get("status") == "pushed")
    failed = sum(1 for f in file_results if f.get("status") != "pushed")
    total_rows = sum(f.get("rows", 0) for f in file_results)
    results = {
        "files": file_results, "total_rows": total_rows,
        "pushed": pushed, "failed": failed,
        "total": len(file_results), "target": target,
    }
    ts = state.now()
    con = state.connect()
    with con:
        con.execute(
            "INSERT INTO batch (batch_id, user_id, config_ref, source_refs, target_json, "
            "status, results_json, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (batch_id, user_id, config_ref,
             state.dumps([f.get("name", "") for f in file_results]),
             state.dumps(target),
             "done" if failed == 0 else "partial",
             state.dumps(results), ts, ts))
    con.close()
    return batch_id


@app.post("/api/batch/push-one")
def batch_push_one(request: Request,
                   file: UploadFile = File(...),
                   config_ref: str = Form(...)) -> dict:
    """Validate and push a single uploaded file. Nothing saved after the request."""
    user = auth.current_user(request)
    auth.check_csrf(request)
    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="ep_push_"))
    name = file.filename or "unnamed.xlsx"
    suffix = Path(name).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"{name}: only .xlsx and .csv files are accepted")
    dest = tmp / name
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        config = batchmod.resolve_config(config_ref, user["user_id"])
        # Validate first
        vresult = batchmod.validate_file(config, name, user["user_id"], {},
                                         source_path=dest)
        if vresult["status"] != "valid":
            entry = {"ref": name, "name": name, "status": "failed",
                     "message": vresult["message"], "rows": 0}
            _record_batch(user["user_id"], config_ref, [entry])
            return entry
        # Push
        where = service.engine.validator.resolve_target(config)
        sheets, columns = service.engine.validator.read_config(config)
        schema_sql = service.engine.validator.render_ddl(
            sheets, columns, where.target, where.prefix, where.id_type)
        database = service.sqlite_path(where.database) if where.target == "sqlite" \
            else where.database
        service.engine.dbmod.load_env(state.PROJECT_ROOT / ".env")
        lines = []
        result = service.engine.executor.execute(
            config, dest, where.target, database, where.prefix,
            schema_sql, 0, lines.append, where.id_type, strict=True,
            source_ref=f"upload:{name}", config_ref=config_ref)
        entry = {"ref": name, "name": name, "status": "pushed",
                 "file_id": result.file_id, "rows": result.total,
                 "per_table": result.per_table}
        target_info = {"target": where.target, "database": database or "",
                       "db_schema": where.db_schema or "", "prefix": where.prefix or ""}
        _record_batch(user["user_id"], config_ref, [entry], target_info)
        return entry
    except (SystemExit, Exception) as exc:
        entry = {"ref": name, "name": name, "status": "failed",
                 "message": str(exc), "rows": 0}
        _record_batch(user["user_id"], config_ref, [entry])
        return entry
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/api/batch/push-upload")
def batch_push_upload(request: Request,
                      files: list[UploadFile] = File(...),
                      config_ref: str = Form(...)) -> dict:
    """Validate and push uploaded source files. Nothing is saved after the request."""
    user = auth.current_user(request)
    auth.check_csrf(request)
    import shutil
    saved, tmp = _save_uploads(files)
    try:
        config = batchmod.resolve_config(config_ref, user["user_id"])
        # Validate all first
        for name, path in saved:
            result = batchmod.validate_file(config, name, user["user_id"], {},
                                            source_path=path)
            if result["status"] != "valid":
                raise HTTPException(status_code=400, detail={
                    "message": f"{name}: {result['message']}",
                    "files": [result]})

        # Build DDL once
        overrides = {}
        where = service.engine.validator.resolve_target(
            config, overrides.get("target"), overrides.get("database"),
            overrides.get("prefix"), overrides.get("id_type"))
        sheets, columns = service.engine.validator.read_config(config)
        schema_sql = service.engine.validator.render_ddl(
            sheets, columns, where.target, where.prefix, where.id_type)
        if where.target == "sqlite":
            database = service.sqlite_path(where.database)
        else:
            database = overrides.get("database") or where.database

        service.engine.dbmod.load_env(state.PROJECT_ROOT / ".env")
        file_results = []
        total_rows = 0
        for name, path in saved:
            lines = []
            try:
                result = service.engine.executor.execute(
                    config, path, where.target, database, where.prefix,
                    schema_sql, 0, lines.append, where.id_type, strict=True,
                    source_ref=f"upload:{name}", config_ref=config_ref)
                file_results.append({
                    "ref": name, "name": name, "status": "pushed",
                    "file_id": result.file_id, "rows": result.total,
                    "per_table": result.per_table})
                total_rows += result.total
            except (SystemExit, Exception) as exc:
                file_results.append({
                    "ref": name, "name": name, "status": "failed",
                    "message": str(exc), "rows": 0})
                break

        pushed = sum(1 for f in file_results if f["status"] == "pushed")
        failed = sum(1 for f in file_results if f["status"] == "failed")
        target_info = {"target": where.target, "database": database or "",
                       "db_schema": where.db_schema or "", "prefix": where.prefix or ""}

        # Record in batch table
        _record_batch(user["user_id"], config_ref, file_results, target_info)

        return {
            "files": file_results, "total_rows": total_rows,
            "pushed": pushed, "failed": failed, "total": len(saved),
            "target": target_info}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------- browser upload


@app.post("/api/upload-workbook")
def upload_workbook(file: UploadFile = File(...), user: dict = auth.Me,
                    _: None = Depends(csrf)) -> dict:
    """Accept a single workbook uploaded via the File System Access API.

    The file is saved to cache/ under a content-addressed name so that the
    same bytes always map to the same ref. Returns an ``upload:<hash>.<ext>``
    ref that resolve() and fingerprint() understand.
    """
    import hashlib

    name = file.filename or "unnamed.xlsx"
    suffix = Path(name).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400,
                            detail=f"{name}: only .xlsx and .csv files are accepted")

    data = file.file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400,
                            detail=f"{name}: file too large "
                                   f"(max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")

    sha = hashlib.sha256(data).hexdigest()[:24]
    cache = sources.CACHE
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"{sha}{suffix}"
    dest.write_bytes(data)

    from urllib.parse import quote
    ref = f"upload:{dest.name}?name={quote(name)}"
    return {"ref": ref, "name": name, "size": len(data), "sha256": sha}


# ------------------------------------------------------- dev path browsing


@app.post("/api/auto-config")
def auto_config(body: dict, user: dict = auth.Me) -> dict:
    """Generate a configuration workbook from a CSV source file's headers."""
    ref = (body.get("ref") or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="no source reference given")
    try:
        path = sources.resolve(ref, "source", user["user_id"])
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="auto-config only works with CSV files")

    import csv_to_config
    table_name = body.get("table_name") or None
    database = body.get("database") or "excel_parser"
    db_schema = body.get("db_schema") or None
    cache = state.PROJECT_ROOT / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    output = cache / f"autoconfig_{state.new_id()[:8]}.xlsx"
    try:
        result = csv_to_config.generate(path, output, table_name=table_name,
                                        database=database, db_schema=db_schema)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"config generation failed: {exc}") from exc
    return {"ok": True, "config_ref": str(result), "name": result.name}


@app.post("/api/test-ref")
def test_ref(body: dict, user: dict = auth.Me) -> dict:
    """Test whether a workbook reference is accessible and valid.

    Resolves the reference (local path, Google Sheets link, or Drive file),
    opens it with openpyxl to confirm it is a real workbook.
    If role=config, also checks that sheet_config and column_config exist.
    """
    ref = (body.get("ref") or "").strip()
    role = (body.get("role") or "source").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="no reference given")
    try:
        path = sources.resolve(ref, "workbook", user["user_id"])
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    import csv_adapter
    try:
        wb = csv_adapter.open_source(path)
        sheets = wb.sheetnames
        wb.close()
    except Exception as exc:
        raise HTTPException(status_code=400,
                            detail="not a valid workbook or CSV file") from exc

    # Config file validation: must have the required configuration sheets
    if role == "config":
        missing = []
        if "sheet_config" not in sheets:
            missing.append("sheet_config")
        if "column_config" not in sheets:
            missing.append("column_config")
        if missing:
            raise HTTPException(status_code=400,
                                detail=f"not a configuration workbook — missing sheet(s): "
                                       f"{', '.join(missing)}. A configuration workbook must "
                                       f"have sheet_config and column_config sheets.")

    display = sources.upload_original_name(ref) if sources.looks_like_upload(ref) else path.name
    return {"ok": True, "name": display, "sheets": sheets,
            "size": path.stat().st_size, "role": role}


# ----------------------------------------------------------- google drive


def drive_guard(call, *args):
    try:
        return call(*args)
    except drive.DriveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/drive/status")
def drive_status(user: dict = auth.Me) -> dict:
    """Is Drive usable at all, and is this user signed in? No token is returned."""
    return drive.status(user["user_id"])


@app.post("/api/drive/connect")
def drive_connect(user: dict = auth.Me, _: None = Depends(csrf)) -> dict:
    """The Google consent URL for this user to open."""
    return {"url": drive_guard(drive.start, user["user_id"])}


@app.get("/api/auth/callback/google")
def drive_callback(state_token: str = Query("", alias="state"), code: str = "",
                   error: str = "") -> RedirectResponse:
    """Where Google sends the browser back.

    No session cookie is required: the single-use `state` issued by /connect is
    what ties the code to a user, and it is deleted as it is used.
    """
    landing = f"{drive.app_url()}/drive-connected?connected="
    if error or not code:
        return RedirectResponse(landing + "0")
    try:
        drive.finish(code, state_token)
    except drive.DriveError:
        return RedirectResponse(landing + "0")
    return RedirectResponse(landing + "1")


@app.post("/api/drive/disconnect")
def drive_disconnect(user: dict = auth.Me, _: None = Depends(csrf)) -> dict:
    drive.disconnect(user["user_id"])
    return {"status": "disconnected"}


@app.get("/api/drive/picker")
def drive_picker(user: dict = auth.Me) -> dict:
    """The credentials the frontend needs to open the Google Picker.

    Returns the API key (public) and a fresh access token. The token is
    short-lived and scoped to drive.readonly — it cannot modify anything.
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=400,
                            detail="Google Picker not configured — set GOOGLE_API_KEY in .env")
    token = drive_guard(drive.access_token, user["user_id"])
    client_id, _ = drive.client()
    return {"api_key": api_key, "access_token": token, "client_id": client_id}


@app.get("/api/drive/files")
def drive_files(user: dict = auth.Me, search: str = Query("", max_length=200),
                folder: str = Query("", max_length=200),
                limit: int = Query(50, ge=1, le=200)) -> dict:
    """Sheets, .xlsx files and folders to pick from - the picker's content."""
    return drive_guard(drive.browse, user["user_id"], search, folder, limit)


@app.get("/api/drive/files/{file_id}")
def drive_file(file_id: str, user: dict = auth.Me) -> dict:
    """One file, so a saved `drive:<id>` reference can be shown by name."""
    item = drive_guard(drive.meta, user["user_id"], file_id)
    return {"id": item["id"], "name": item["name"], "mime_type": item["mimeType"],
            "modified_at": item.get("modifiedTime"), "ref": f"drive:{item['id']}"}
