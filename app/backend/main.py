"""Excel Parser - HTTP API.

Every endpoint except /api/auth/login and /api/health requires a session, and
every project and run is filtered by the caller's user_id, so one user never
sees another's work. The parser itself is imported unchanged from tools/.

    uvicorn main:app --port 8000            (run.sh does this for you)
"""
import logging
import os

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
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
    sql = ("SELECT r.*, p.name AS project_name FROM run r "
           "JOIN project p ON p.project_id = r.project_id WHERE r.user_id = %s")
    params = [user["user_id"]]
    if project_id:
        sql += " AND r.project_id = %s"
        params.append(project_id)
    sql += " ORDER BY r.started_at DESC LIMIT %s"
    params.append(limit)
    con = state.connect()
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [{
        "run_id": r["run_id"], "project_id": r["project_id"],
        "project_name": r["project_name"], "started_at": r["started_at"],
        "finished_at": r["finished_at"], "status": r["status"], "target": r["target"],
        "database": r["database"], "db_schema": r["db_schema"], "prefix": r["prefix"],
        "row_total": r["row_total"], "file_id": r["file_id"],
        "source_name": r["source_name"], "config_name": r["config_name"],
    } for r in rows]


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


@app.get("/api/local-workbooks")
def local_workbooks(user: dict = auth.Me) -> dict:
    """The .xlsx and .csv files inside the project - the only local paths accepted."""
    return {"root": str(state.PROJECT_ROOT), "files": sources.list_workbooks()}


@app.get("/api/workbook-dir")
def browse_workbook_dir(user: dict = auth.Me,
                        folder: str = Query("", max_length=500)) -> dict:
    """Browse .xlsx files in the configured WORKBOOK_DIR."""
    try:
        return sources.browse_workbook_dir(folder)
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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

    return {"ok": True, "name": path.name, "sheets": sheets,
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
