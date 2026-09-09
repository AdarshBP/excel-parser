"""Google Drive as a source: OAuth sign-in, file browsing, and download.

The user picks a file in the app instead of pasting a link; the reference stored
on the project is `drive:<file id>` (with the name kept only for display), and
`sources.resolve()` turns it into an .xlsx on disk like every other source.

Credentials come from the environment - GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
of a Google Cloud OAuth "Web application" client - never from a workbook or this
file. Without them the endpoints answer `configured: false` and the rest of the
app is unaffected.

Tokens are per user, kept in the application database, never logged and never
returned by the API. Only the refresh token is long-lived; access tokens are
refreshed here as they expire.
"""
import base64
import datetime as dt
import hashlib
import os
import urllib.parse
from pathlib import Path

import requests

import state

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# read-only, and only what is needed to show who is connected
SCOPES = ("https://www.googleapis.com/auth/drive.readonly "
          "https://www.googleapis.com/auth/userinfo.email")

SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FOLDER_MIME = "application/vnd.google-apps.folder"
FIELDS = ("files(id,name,mimeType,modifiedTime,size,iconLink,webViewLink,owners(emailAddress))"
          ",nextPageToken")

TIMEOUT = 30
MAX_BYTES = 40 * 1024 * 1024
STATE_TTL_MINUTES = 10


class DriveError(Exception):
    """Anything the user can act on - shown as a 400."""


# --------------------------------------------------------------- settings


def client() -> tuple:
    return (os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            os.environ.get("GOOGLE_CLIENT_SECRET", "").strip())


def redirect_uri() -> str:
    return os.environ.get("GOOGLE_REDIRECT_URI",
                          "http://localhost:8000/api/auth/callback/google").strip()


def app_url() -> str:
    return os.environ.get("APP_FRONTEND_URL", "http://localhost:4200").strip()


def configured() -> bool:
    client_id, secret = client()
    return bool(client_id and secret)


def require_configured() -> tuple:
    client_id, secret = client()
    if not (client_id and secret):
        raise DriveError("Google Drive is not configured on the server - set "
                         "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")
    return client_id, secret


# ------------------------------------------------------------------ token


def _row(user_id: str):
    con = state.connect()
    row = con.execute("SELECT * FROM google_token WHERE user_id = %s", (user_id,)).fetchone()
    con.close()
    return row


def status(user_id: str) -> dict:
    """What the UI needs to decide between "Connect" and the file picker."""
    row = _row(user_id)
    return {"configured": configured(), "connected": row is not None,
            "email": row["email"] if row else None,
            "connected_at": row["connected_at"] if row else None,
            "redirect_uri": redirect_uri()}


def _store(user_id: str, token: dict, email: str, refresh: str) -> None:
    expires = (dt.datetime.now(dt.timezone.utc)
               + dt.timedelta(seconds=int(token.get("expires_in", 3600)) - 60))
    con = state.connect()
    with con:
        con.execute(
            "INSERT INTO google_token (user_id, access_token, refresh_token, expires_at, "
            "scope, email, connected_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT(user_id) DO UPDATE SET access_token = excluded.access_token, "
            "refresh_token = excluded.refresh_token, expires_at = excluded.expires_at, "
            "scope = excluded.scope, email = excluded.email, "
            "connected_at = excluded.connected_at",
            (user_id, token["access_token"], refresh, expires.isoformat(timespec="seconds"),
             token.get("scope", ""), email, state.now()))
    con.close()


def disconnect(user_id: str) -> None:
    """Forget the tokens, and tell Google to drop them too."""
    row = _row(user_id)
    if row and row["refresh_token"]:
        try:
            requests.post(REVOKE_URL, data={"token": row["refresh_token"]}, timeout=TIMEOUT)
        except requests.RequestException:
            pass                                  # local removal still happens
    con = state.connect()
    with con:
        con.execute("DELETE FROM google_token WHERE user_id = %s", (user_id,))
    con.close()


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def start(user_id: str) -> str:
    """The Google consent URL to send the browser to.

    `state` and a PKCE verifier are stored here and both are required back, so a
    code obtained by anyone else cannot be redeemed against this server.
    """
    client_id, _ = require_configured()
    token, verifier = state.new_token(), state.new_token()
    con = state.connect()
    with con:
        con.execute("DELETE FROM google_oauth_state WHERE user_id = %s", (user_id,))
        con.execute("INSERT INTO google_oauth_state (state, user_id, code_verifier, "
                    "created_at) VALUES (%s, %s, %s, %s)",
                    (token, user_id, verifier, state.now()))
    con.close()
    # Only force consent if no token exists yet (first connect).
    # Re-connecting reuses the existing refresh token without a consent screen.
    existing = _row(user_id)
    params = {
        "client_id": client_id, "redirect_uri": redirect_uri(),
        "response_type": "code", "scope": SCOPES, "state": token,
        "code_challenge": _challenge(verifier), "code_challenge_method": "S256",
        "access_type": "offline", "include_granted_scopes": "true"}
    if not existing:
        params["prompt"] = "consent"
    query = urllib.parse.urlencode(params)
    return f"{AUTH_URL}?{query}"


def finish(code: str, oauth_state: str) -> str:
    """Exchange the code for tokens. Returns the user_id that connected."""
    client_id, secret = require_configured()
    con = state.connect()
    row = con.execute("SELECT * FROM google_oauth_state WHERE state = %s",
                      (oauth_state,)).fetchone()
    if row is not None:
        with con:
            con.execute("DELETE FROM google_oauth_state WHERE state = %s", (oauth_state,))
    con.close()
    if row is None:
        raise DriveError("this sign-in link is not one we issued - start again")
    started = dt.datetime.fromisoformat(row["created_at"])
    if dt.datetime.now(dt.timezone.utc) - started > dt.timedelta(minutes=STATE_TTL_MINUTES):
        raise DriveError("the sign-in took too long - start again")

    token = _post(TOKEN_URL, {"code": code, "client_id": client_id,
                              "client_secret": secret, "redirect_uri": redirect_uri(),
                              "code_verifier": row["code_verifier"],
                              "grant_type": "authorization_code"})
    refresh = token.get("refresh_token")
    if not refresh:
        old = _row(row["user_id"])
        refresh = old["refresh_token"] if old else ""
    email = ""
    try:
        reply = requests.get(USERINFO_URL, timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {token['access_token']}"})
        email = reply.json().get("email", "") if reply.status_code == 200 else ""
    except (requests.RequestException, ValueError):
        pass
    _store(row["user_id"], token, email, refresh)
    return row["user_id"]


def _post(url: str, data: dict) -> dict:
    try:
        reply = requests.post(url, data=data, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise DriveError(f"could not reach Google: {exc}") from exc
    if reply.status_code != 200:
        # Google's body can carry the client secret back in an echoed request; only
        # its own error code is safe (and useful) to show.
        try:
            why = reply.json().get("error", "")
        except ValueError:
            why = ""
        raise DriveError(f"Google refused the sign-in ({reply.status_code} {why})")
    return reply.json()


def access_token(user_id: str) -> str:
    """A valid access token, refreshed if the stored one has expired."""
    client_id, secret = require_configured()
    row = _row(user_id)
    if row is None:
        raise DriveError("connect Google Drive first")
    if dt.datetime.fromisoformat(row["expires_at"]) > dt.datetime.now(dt.timezone.utc):
        return row["access_token"]
    if not row["refresh_token"]:
        raise DriveError("the Google sign-in has expired - connect Drive again")
    token = _post(TOKEN_URL, {"refresh_token": row["refresh_token"],
                              "client_id": client_id, "client_secret": secret,
                              "grant_type": "refresh_token"})
    _store(user_id, token, row["email"], row["refresh_token"])
    return token["access_token"]


def _get(user_id: str, url: str, params: dict = None, stream: bool = False):
    try:
        reply = requests.get(url, params=params, stream=stream, timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {access_token(user_id)}"})
    except requests.RequestException as exc:
        raise DriveError(f"could not reach Google Drive: {exc}") from exc
    if reply.status_code == 401:
        raise DriveError("Google Drive rejected the sign-in - connect Drive again")
    if reply.status_code == 403:
        raise DriveError("Google Drive refused access to that file")
    if reply.status_code == 404:
        raise DriveError("that Drive file no longer exists, or is not shared with you")
    if reply.status_code != 200:
        raise DriveError(f"Google Drive returned HTTP {reply.status_code}")
    return reply


# ------------------------------------------------------------- browsing


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def browse(user_id: str, search: str = "", folder: str = "", limit: int = 50) -> dict:
    """Spreadsheets, .xlsx files and folders the user can see, newest first."""
    kinds = (f"(mimeType = '{SHEET_MIME}' or mimeType = '{XLSX_MIME}' "
             f"or mimeType = '{FOLDER_MIME}')")
    clauses = ["trashed = false", kinds]
    if search.strip():
        clauses.append(f"name contains '{_quote(search.strip())}'")
    if folder.strip():
        clauses.append(f"'{_quote(folder.strip())}' in parents")
    reply = _get(user_id, FILES_URL, {
        "q": " and ".join(clauses), "fields": FIELDS,
        "pageSize": max(1, min(limit, 200)), "orderBy": "folder,modifiedTime desc",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
        "spaces": "drive"})
    files = []
    for item in reply.json().get("files", []):
        files.append({
            "id": item["id"], "name": item["name"], "mime_type": item["mimeType"],
            "kind": ("folder" if item["mimeType"] == FOLDER_MIME
                     else "sheet" if item["mimeType"] == SHEET_MIME else "xlsx"),
            "modified_at": item.get("modifiedTime"), "size": item.get("size"),
            "link": item.get("webViewLink"),
            "owner": (item.get("owners") or [{}])[0].get("emailAddress", ""),
            "ref": f"drive:{item['id']}",
        })
    return {"files": files, "folder": folder, "search": search}


def meta(user_id: str, file_id: str) -> dict:
    reply = _get(user_id, f"{FILES_URL}/{urllib.parse.quote(file_id)}", {
        "fields": "id,name,mimeType,modifiedTime,size,md5Checksum",
        "supportsAllDrives": "true"})
    item = reply.json()
    if item.get("mimeType") not in (SHEET_MIME, XLSX_MIME):
        raise DriveError(f"{item.get('name', file_id)} is not a Google Sheet or an .xlsx "
                         "workbook")
    return item


# In-memory cache for Drive metadata to reduce API calls during polling.
# Key: (user_id, file_id), Value: (timestamp, item dict)
_meta_cache: dict = {}
_META_TTL = 30  # seconds


def cached_meta(user_id: str, file_id: str) -> dict:
    """Drive metadata, cached for 30 seconds to stay within quota."""
    key = (user_id, file_id)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    cached = _meta_cache.get(key)
    if cached and now - cached[0] < _META_TTL:
        return cached[1]
    item = meta(user_id, file_id)
    _meta_cache[key] = (now, item)
    return item


def invalidate_meta(user_id: str, file_id: str) -> None:
    """Drop the cached metadata so the next call fetches fresh data."""
    _meta_cache.pop((user_id, file_id), None)


def download(user_id: str, file_id: str, cache: Path) -> Path:
    """The file as .xlsx on disk, always re-downloaded fresh.

    No local caching by modifiedTime — every download hits Google to ensure
    the user sees the latest version after editing a Sheet.
    """
    item = meta(user_id, file_id)
    # Invalidate meta cache so next fingerprint sees the new modifiedTime
    invalidate_meta(user_id, file_id)

    cache.mkdir(parents=True, exist_ok=True)
    # Fixed filename per file_id so re-downloads overwrite in place
    path = cache / f"drive_{file_id}.xlsx"

    if item["mimeType"] == SHEET_MIME:
        reply = _get(user_id, f"{FILES_URL}/{urllib.parse.quote(file_id)}/export",
                     {"mimeType": XLSX_MIME}, stream=True)
    else:
        reply = _get(user_id, f"{FILES_URL}/{urllib.parse.quote(file_id)}",
                     {"alt": "media", "supportsAllDrives": "true"}, stream=True)

    size = 0
    tmp = path.with_suffix(".part")
    with tmp.open("wb") as out:
        for chunk in reply.iter_content(chunk_size=1 << 16):
            size += len(chunk)
            if size > MAX_BYTES:
                out.close()
                tmp.unlink(missing_ok=True)
                raise DriveError(f"{item['name']} is larger than 40 MB")
            out.write(chunk)
    tmp.replace(path)
    return path
