"""Checks for the Google Drive source that need no Google account.

Run from this directory:  python3 -m pytest test_drive.py -q
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import drive                                                # noqa: E402
import sources                                              # noqa: E402
import state                                                # noqa: E402


@pytest.fixture(autouse=True)
def app_db(tmp_path, monkeypatch):
    """A throwaway state.db, so nothing here touches the running app's data."""
    monkeypatch.setattr(state, "DB_PATH", tmp_path / "state.db")
    state.init()
    con = state.connect()
    with con:
        con.execute("INSERT INTO user (user_id, username, password_hash, created_at, "
                    "must_change_password) VALUES ('u1', 'a', 'x', ?, 0)", (state.now(),))
        con.execute("INSERT INTO user (user_id, username, password_hash, created_at, "
                    "must_change_password) VALUES ('u2', 'b', 'x', ?, 0)", (state.now(),))
    con.close()
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)


def credentials(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "FAKE-CLIENT-ID-FOR-TESTING")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "FAKE-SECRET-FOR-TESTING")


def store(user_id, expires, refresh="FAKE-REFRESH"):
    con = state.connect()
    with con:
        con.execute("INSERT INTO google_token (user_id, access_token, refresh_token, "
                    "expires_at, scope, email, connected_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, f"FAKE-ACCESS-{user_id}", refresh,
                     expires.isoformat(timespec="seconds"), drive.SCOPES,
                     f"{user_id}@example.com", state.now()))
    con.close()


# ------------------------------------------------------------- references


def test_reference_kinds():
    assert sources.kind_of("examples/01_simple/sales_source.xlsx") == "local"
    assert sources.kind_of("https://docs.google.com/spreadsheets/d/abc123/edit") == "sheet"
    assert sources.kind_of("drive:1AbC-dEfG_hIjKlMnOpQ") == "drive"


def test_drive_file_id_is_validated():
    assert sources.drive_file_id("drive:1AbC-dEfG_hIjKlMnOpQ") == "1AbC-dEfG_hIjKlMnOpQ"
    assert sources.drive_file_id("drive:1AbC-dEfG_hIjKlMnOpQ?name=Sales.xlsx") \
        == "1AbC-dEfG_hIjKlMnOpQ"
    for bad in ("drive:", "drive:short", "drive:../../etc/passwd",
                "drive:abcdefghijk'; drop table x"):
        with pytest.raises(sources.SourceError):
            sources.drive_file_id(bad)


def test_a_drive_reference_needs_a_user():
    with pytest.raises(sources.SourceError):
        sources.resolve("drive:1AbC-dEfG_hIjKlMnOpQ", "source")


# ------------------------------------------------------------ configuration


def test_unconfigured_status_says_so_and_refuses_to_start():
    assert drive.configured() is False
    assert drive.status("u1") == {"configured": False, "connected": False, "email": None,
                                 "connected_at": None,
                                 "redirect_uri": drive.redirect_uri()}
    with pytest.raises(drive.DriveError):
        drive.start("u1")


# -------------------------------------------------------------- oauth flow


def test_start_issues_one_state_with_pkce(monkeypatch):
    credentials(monkeypatch)
    url = drive.start("u1")
    con = state.connect()
    rows = con.execute("SELECT * FROM google_oauth_state").fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0]["user_id"] == "u1"
    assert f"state={rows[0]['state']}" in url
    assert f"code_challenge={drive._challenge(rows[0]['code_verifier'])}" in url
    assert "code_challenge_method=S256" in url
    assert "drive.readonly" in url
    assert "FAKE-SECRET-FOR-TESTING" not in url        # the secret never leaves the server

    drive.start("u1")                                  # restarting replaces, never piles up
    con = state.connect()
    assert con.execute("SELECT count(*) c FROM google_oauth_state").fetchone()["c"] == 1
    con.close()


def test_an_unknown_state_is_refused(monkeypatch):
    credentials(monkeypatch)
    with pytest.raises(drive.DriveError):
        drive.finish("FAKE-CODE", "not-a-state-we-issued")


def test_an_expired_state_is_refused(monkeypatch):
    credentials(monkeypatch)
    drive.start("u1")
    stale = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(minutes=drive.STATE_TTL_MINUTES + 1))
    con = state.connect()
    with con:
        con.execute("UPDATE google_oauth_state SET created_at = ?",
                    (stale.isoformat(timespec="seconds"),))
        used = con.execute("SELECT state FROM google_oauth_state").fetchone()["state"]
    con.close()
    with pytest.raises(drive.DriveError):
        drive.finish("FAKE-CODE", used)


def test_a_state_can_only_be_used_once(monkeypatch):
    credentials(monkeypatch)
    drive.start("u1")
    con = state.connect()
    used = con.execute("SELECT state FROM google_oauth_state").fetchone()["state"]
    con.close()
    posted = {}

    def fake_post(url, data):
        posted.update(data)
        return {"access_token": "FAKE-ACCESS", "refresh_token": "FAKE-REFRESH",
                "expires_in": 3600, "scope": drive.SCOPES}

    monkeypatch.setattr(drive, "_post", fake_post)
    monkeypatch.setattr(drive.requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        drive.requests.RequestException("no network in tests")))
    assert drive.finish("FAKE-CODE", used) == "u1"
    assert posted["code_verifier"]                     # PKCE is proved, not just requested
    with pytest.raises(drive.DriveError):
        drive.finish("FAKE-CODE", used)


# ------------------------------------------------------------------ tokens


def test_a_live_token_is_used_as_is(monkeypatch):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    monkeypatch.setattr(drive, "_post", lambda *a: pytest.fail("refreshed too early"))
    assert drive.access_token("u1") == "FAKE-ACCESS-u1"


def test_an_expired_token_is_refreshed_and_the_refresh_token_kept(monkeypatch):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1))
    monkeypatch.setattr(drive, "_post", lambda url, data: {
        "access_token": "FAKE-ACCESS-NEW", "expires_in": 3600})   # Google sends no refresh
    assert drive.access_token("u1") == "FAKE-ACCESS-NEW"
    con = state.connect()
    row = con.execute("SELECT * FROM google_token WHERE user_id = 'u1'").fetchone()
    con.close()
    assert row["refresh_token"] == "FAKE-REFRESH"
    assert row["email"] == "u1@example.com"


def test_users_do_not_share_a_sign_in(monkeypatch):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    assert drive.status("u1")["connected"] is True
    assert drive.status("u2")["connected"] is False
    with pytest.raises(drive.DriveError):
        drive.access_token("u2")


def test_status_never_carries_a_token(monkeypatch):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    assert "FAKE-ACCESS-u1" not in str(drive.status("u1"))
    assert "FAKE-REFRESH" not in str(drive.status("u1"))


def test_disconnect_forgets_the_token(monkeypatch):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    monkeypatch.setattr(drive.requests, "post", lambda *a, **k: None)
    drive.disconnect("u1")
    assert drive.status("u1")["connected"] is False


# ---------------------------------------------------------------- browsing


class FakeReply:
    def __init__(self, payload=None, chunks=(), status=200):
        self.payload, self.chunks, self.status_code = payload or {}, chunks, status
        self.headers = {}

    def json(self):
        return self.payload

    def iter_content(self, chunk_size=0):
        return iter(self.chunks)


def test_a_search_term_cannot_break_out_of_the_drive_query(monkeypatch):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    seen = {}

    def fake_get(user_id, url, params=None, stream=False):
        seen.update(params or {})
        return FakeReply({"files": []})

    monkeypatch.setattr(drive, "_get", fake_get)
    drive.browse("u1", search="quarter' or name contains 'secret", folder="f1")
    query = seen["q"]
    assert "trashed = false" in query
    assert r"name contains 'quarter\' or name contains \'secret'" in query
    assert "'f1' in parents" in query


def test_browse_returns_pickable_references(monkeypatch):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    monkeypatch.setattr(drive, "_get", lambda *a, **k: FakeReply({"files": [
        {"id": "F1", "name": "Team", "mimeType": drive.FOLDER_MIME},
        {"id": "S1", "name": "Sales", "mimeType": drive.SHEET_MIME,
         "modifiedTime": "2026-01-01T00:00:00Z"},
        {"id": "X1", "name": "Ledger.xlsx", "mimeType": drive.XLSX_MIME, "size": "1024"},
    ]}))
    files = drive.browse("u1")["files"]
    assert [f["kind"] for f in files] == ["folder", "sheet", "xlsx"]
    assert [f["ref"] for f in files] == ["drive:F1", "drive:S1", "drive:X1"]


# ---------------------------------------------------------------- download


def test_a_sheet_is_exported_and_an_xlsx_is_downloaded(monkeypatch, tmp_path):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    calls = []

    def fake_get(user_id, url, params=None, stream=False):
        calls.append((url, dict(params or {})))
        if url.endswith("/files/S1") or url.endswith("/files/X1"):
            mime = drive.SHEET_MIME if url.endswith("S1") else drive.XLSX_MIME
            return FakeReply({"id": url[-2:], "name": "Book", "mimeType": mime,
                              "modifiedTime": "2026-01-01T00:00:00Z"})
        return FakeReply(chunks=[b"PK\x03\x04book"])

    monkeypatch.setattr(drive, "_get", fake_get)

    sheet = drive.download("u1", "S1", tmp_path)
    assert sheet.read_bytes() == b"PK\x03\x04book" and sheet.suffix == ".xlsx"
    assert calls[1][0].endswith("/export") and calls[1][1]["mimeType"] == drive.XLSX_MIME

    calls.clear()
    xlsx = drive.download("u1", "X1", tmp_path)
    assert xlsx.is_file() and calls[1][1]["alt"] == "media"


def test_an_unchanged_file_is_not_downloaded_twice(monkeypatch, tmp_path):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    downloads = []

    def fake_get(user_id, url, params=None, stream=False):
        if url.endswith("/files/S1"):
            return FakeReply({"id": "S1", "name": "Book", "mimeType": drive.SHEET_MIME,
                              "modifiedTime": "2026-01-01T00:00:00Z"})
        downloads.append(url)
        return FakeReply(chunks=[b"PK\x03\x04book"])

    monkeypatch.setattr(drive, "_get", fake_get)
    first = drive.download("u1", "S1", tmp_path)
    again = drive.download("u1", "S1", tmp_path)
    assert first == again and len(downloads) == 1


def test_a_huge_file_is_refused_without_being_kept(monkeypatch, tmp_path):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    monkeypatch.setattr(drive, "MAX_BYTES", 16)

    def fake_get(user_id, url, params=None, stream=False):
        if url.endswith("/files/S1"):
            return FakeReply({"id": "S1", "name": "Huge", "mimeType": drive.SHEET_MIME,
                              "modifiedTime": "2026-01-01T00:00:00Z"})
        return FakeReply(chunks=[b"x" * 32])

    monkeypatch.setattr(drive, "_get", fake_get)
    with pytest.raises(drive.DriveError):
        drive.download("u1", "S1", tmp_path)
    assert list(tmp_path.glob("*.xlsx")) == [] and list(tmp_path.glob("*.part")) == []


def test_a_document_is_not_accepted_as_a_workbook(monkeypatch, tmp_path):
    credentials(monkeypatch)
    store("u1", dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30))
    monkeypatch.setattr(drive, "_get", lambda *a, **k: FakeReply(
        {"id": "D1", "name": "Notes", "mimeType": "application/vnd.google-apps.document"}))
    with pytest.raises(drive.DriveError):
        drive.download("u1", "D1", tmp_path)
