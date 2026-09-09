"""Where a workbook comes from. Three kinds of reference:

    local   examples/01_simple/sales_source.xlsx   a path inside the project
            /abs/path/inside/WORKBOOK_DIR/file.xlsx  or the configured workbook dir
    link    https://docs.google.com/spreadsheets/d/<id>/edit   a shared link
    drive   drive:<file id>                        picked from Google Drive

All three are resolved to an .xlsx on disk, so validator/executor/preview never
learn where the file came from. A fingerprint (sha256 of the bytes) is what the
5-second status poll compares.
"""
import hashlib
import os
import re
import shutil
from pathlib import Path

import requests

import drive
import state

CACHE = state.APP_DIR / "cache"
DRIVE_PREFIX = "drive:"
ALLOWED_SUFFIXES = {".xlsx", ".xlsm", ".csv"}
SHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
GID = re.compile(r"[#&?]gid=(\d+)")
TIMEOUT = 30
MAX_BYTES = 40 * 1024 * 1024


class SourceError(Exception):
    """A reference that cannot be used - shown to the user as a 400."""


def looks_like_sheet(value: str) -> bool:
    return value.strip().startswith("http") and "docs.google.com" in value


def looks_like_drive(value: str) -> bool:
    return value.strip().startswith(DRIVE_PREFIX)


def kind_of(value: str) -> str:
    value = value or ""
    if looks_like_drive(value):
        return "drive"
    return "sheet" if looks_like_sheet(value) else "local"


def drive_file_id(value: str) -> str:
    """`drive:<id>` -> the id. A display name may follow as `?name=...`."""
    rest = value.strip()[len(DRIVE_PREFIX):].split("?", 1)[0].strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,120}", rest):
        raise SourceError(f"{value!r} is not a Google Drive file reference")
    return rest


def workbook_dir() -> Path | None:
    """The configured external workbook directory, or None."""
    raw = os.environ.get("WORKBOOK_DIR", "").strip()
    if not raw:
        return None
    path = Path(raw).resolve()
    if not path.is_dir():
        return None
    return path


def _safe_local(value: str) -> Path:
    """A local path, forced to stay inside the project directory or WORKBOOK_DIR."""
    raw = Path(value.strip()).expanduser()
    path = (raw if raw.is_absolute() else state.PROJECT_ROOT / raw).resolve()
    root = state.PROJECT_ROOT.resolve()
    wdir = workbook_dir()
    inside_project = (root == path or root in path.parents)
    inside_wdir = wdir and (wdir == path or wdir in path.parents)
    if not inside_project and not inside_wdir:
        raise SourceError("that path is outside the allowed directories")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise SourceError(f"{path.name}: expected an .xlsx workbook or .csv file")
    if not path.is_file():
        raise SourceError(f"{path.name} does not exist")
    return path


def _sheet_export_url(value: str) -> str:
    match = SHEET_ID.search(value)
    if not match:
        raise SourceError("that does not look like a Google Sheets link "
                          "(https://docs.google.com/spreadsheets/d/<id>/...)")
    url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=xlsx"
    gid = GID.search(value)
    return f"{url}&gid={gid.group(1)}" if gid else url


def _download_sheet(value: str, label: str) -> Path:
    """Fetch a Sheet as .xlsx. Public link-shared sheets need no credentials."""
    url = _sheet_export_url(value)
    headers = {}
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if token:                       # optional: read-only token for private sheets
        headers["Authorization"] = f"Bearer {token}"
    try:
        reply = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        raise SourceError(f"could not reach Google Sheets: {exc}") from exc

    if reply.status_code in (401, 403, 404) or "text/html" in \
            reply.headers.get("content-type", ""):
        raise SourceError(
            "Google refused to export that sheet. Share it as 'Anyone with the link "
            "- Viewer', or provide a read-only credential in the server environment.")
    if reply.status_code != 200:
        raise SourceError(f"Google Sheets returned HTTP {reply.status_code}")
    if len(reply.content) > MAX_BYTES:
        raise SourceError("that sheet exports to more than 40 MB")

    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{label}_{hashlib.sha256(url.encode()).hexdigest()[:16]}.xlsx"
    path.write_bytes(reply.content)
    return path


def _download_drive(value: str, user_id: str) -> Path:
    """A file picked from Drive, using the signed-in user's own read-only token."""
    if not user_id:
        raise SourceError("a Google Drive file can only be read for a signed-in user")
    try:
        return drive.download(user_id, drive_file_id(value), CACHE)
    except drive.DriveError as exc:
        raise SourceError(str(exc)) from exc


def resolve(value: str, label: str = "workbook", user_id: str = None) -> Path:
    """A local .xlsx for this reference, fetching it from Google if needed."""
    value = (value or "").strip()
    if not value:
        raise SourceError(f"no {label} given")
    if looks_like_drive(value):
        return _download_drive(value, user_id)
    return _download_sheet(value, label) if looks_like_sheet(value) else _safe_local(value)


def fingerprint(value: str, label: str = "workbook", user_id: str = None) -> dict:
    """{sha256, size, name} - what the poll compares to spot an edited sheet.

    For Drive files, uses the cached metadata modifiedTime instead of
    re-downloading the entire file — one cheap metadata call per 30 seconds
    instead of a full export on every 5-second poll.
    """
    value = (value or "").strip()
    if looks_like_drive(value):
        file_id = drive_file_id(value)
        item = drive.cached_meta(user_id, file_id)
        # Use modifiedTime as a change fingerprint — no download needed
        modified = item.get("modifiedTime", "")
        fake_sha = hashlib.sha256(f"{file_id}|{modified}".encode()).hexdigest()
        return {"sha256": fake_sha, "size": int(item.get("size", 0)),
                "name": item.get("name", file_id)}

    path = resolve(value, label, user_id)
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "name": path.name}


def snapshot(path: Path, run_id: str, label: str) -> str:
    """Keep the exact bytes a run used, so history can be re-inspected."""
    folder = state.APP_DIR / "snapshots" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{label}{path.suffix}"
    shutil.copy2(path, target)
    return str(target)


def list_workbooks() -> list:
    """Every .xlsx and .csv inside the project - what the dev-mode path picker offers."""
    root = state.PROJECT_ROOT.resolve()
    skip = {"node_modules", ".git", "cache", "snapshots", "uploads", "dist", ".angular"}
    found = []
    for ext in ("*.xlsx", "*.csv"):
        for path in sorted(root.rglob(ext)):
            if skip & set(path.relative_to(root).parts):
                continue
            found.append(str(path.relative_to(root)))
    found.sort()
    return found


def browse_workbook_dir(folder: str = "") -> dict:
    """List .xlsx files and subfolders inside WORKBOOK_DIR for the browser picker.

    Returns {root, folder, items: [{name, path, kind, size}]}.
    `folder` is a relative path inside WORKBOOK_DIR to browse into.
    """
    wdir = workbook_dir()
    if not wdir:
        return {"root": None, "folder": "", "items": []}

    if folder:
        target = (wdir / folder).resolve()
        if wdir not in target.parents and wdir != target:
            raise SourceError("folder must be inside the workbook directory")
    else:
        target = wdir

    if not target.is_dir():
        raise SourceError(f"{target} is not a directory")

    items = []
    for entry in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            items.append({"name": entry.name, "path": str(entry.relative_to(wdir)),
                          "kind": "folder", "size": None})
        elif entry.suffix.lower() in ALLOWED_SUFFIXES:
            items.append({"name": entry.name, "path": str(entry),
                          "kind": "file", "size": entry.stat().st_size})
    return {"root": str(wdir), "folder": folder, "items": items}
