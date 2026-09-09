"""Local username/password login with a server-side session cookie.

Passwords are stored as Argon2id hashes; the browser only ever holds an opaque
HttpOnly cookie, and every session is revocable from the application database.
"""
import datetime as dt
import hashlib
import hmac
import os

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response

import state

COOKIE = "ep_session"
CSRF_COOKIE = "ep_csrf"
CSRF_HEADER = "x-csrf-token"
SESSION_HOURS = 12
MAX_FAILED = 5
LOCK_MINUTES = 5
MIN_PASSWORD = 8
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def _token_hash(token: str) -> str:
    """Sessions are stored hashed, so a copy of state.db is not a set of logins."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(username: str, password: str, must_change: bool = False) -> str:
    username = username.strip().lower()
    if not username or len(password) < MIN_PASSWORD:
        raise ValueError("username is required and the password must be "
                         f"{MIN_PASSWORD}+ characters")
    user_id = state.new_id()
    con = state.connect()
    with con:
        con.execute(
            'INSERT INTO "user" (user_id, username, password_hash, created_at, '
            "must_change_password) VALUES (%s, %s, %s, %s, %s)",
            (user_id, username, hash_password(password), state.now(), int(must_change)))
    con.close()
    return user_id


def set_password(username: str, password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"the password must be {MIN_PASSWORD}+ characters")
    con = state.connect()
    with con:
        cur = con.execute(
            'UPDATE "user" SET password_hash = %s, must_change_password = 0, '
            "failed_attempts = 0, locked_until = NULL WHERE username = %s",
            (hash_password(password), username.strip().lower()))
        changed = cur.rowcount
    con.close()
    if not changed:
        raise ValueError(f"no such user: {username}")


def _locked(row) -> bool:
    until = row["locked_until"]
    return bool(until and until > state.now())


def login(username: str, password: str, response: Response) -> dict:
    """Verify the credentials and set the session cookie. Vague on failure."""
    con = state.connect()
    row = con.execute('SELECT * FROM "user" WHERE username = %s',
                      (username.strip().lower(),)).fetchone()
    generic = HTTPException(status_code=401, detail="invalid username or password")

    if row is None:
        con.close()
        # Spend the same time as a real verification so absence is not timeable.
        hasher.hash(password)
        raise generic
    if _locked(row):
        con.close()
        raise HTTPException(status_code=429,
                            detail="too many failed attempts, try again in a few minutes")

    try:
        hasher.verify(row["password_hash"], password)
    except (VerifyMismatchError, InvalidHashError):
        failed = row["failed_attempts"] + 1
        locked = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=LOCK_MINUTES)
                  ).isoformat(timespec="seconds") if failed >= MAX_FAILED else None
        with con:
            con.execute('UPDATE "user" SET failed_attempts = %s, locked_until = %s '
                        "WHERE user_id = %s", (failed, locked, row["user_id"]))
        con.close()
        raise generic from None

    token = state.new_token()
    expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=SESSION_HOURS)
               ).isoformat(timespec="seconds")
    with con:
        con.execute('UPDATE "user" SET failed_attempts = 0, locked_until = NULL '
                    "WHERE user_id = %s", (row["user_id"],))
        con.execute("INSERT INTO session (session_id, user_id, created_at, expires_at) "
                    "VALUES (%s, %s, %s, %s)",
                    (_token_hash(token), row["user_id"], state.now(), expires))
    con.close()

    csrf = state.new_token()
    secure = _https_only()
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=secure,
                        max_age=SESSION_HOURS * 3600, path="/")
    # Readable by the app on purpose: it is echoed back in X-CSRF-Token so a
    # cross-site form cannot make a state-changing call with the session cookie.
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="lax", secure=secure,
                        max_age=SESSION_HOURS * 3600, path="/")
    return {"username": row["username"],
            "must_change_password": bool(row["must_change_password"])}


def _https_only() -> bool:
    """Cookies are Secure everywhere except the documented local dev run."""
    return os.environ.get("APP_ENV", "dev").lower() != "dev"


def check_csrf(request: Request) -> None:
    """Double-submit check on every state-changing request."""
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    header = request.headers.get(CSRF_HEADER) or ""
    if not cookie or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="missing or stale CSRF token")


def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        con = state.connect()
        with con:
            con.execute("UPDATE session SET revoked = 1 WHERE session_id = %s",
                        (_token_hash(token),))
        con.close()
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def current_user(request: Request) -> dict:
    """FastAPI dependency: the logged-in user, or 401."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not logged in")
    con = state.connect()
    row = con.execute(
        'SELECT u.user_id, u.username, u.must_change_password FROM session s '
        'JOIN "user" u ON u.user_id = s.user_id '
        "WHERE s.session_id = %s AND s.revoked = 0 AND s.expires_at > %s",
        (_token_hash(token), state.now())).fetchone()
    con.close()
    if row is None:
        raise HTTPException(status_code=401, detail="session expired, log in again")
    return {"user_id": row["user_id"], "username": row["username"],
            "must_change_password": bool(row["must_change_password"])}


def change_password(user: dict, current: str, new: str) -> None:
    con = state.connect()
    row = con.execute('SELECT password_hash FROM "user" WHERE user_id = %s',
                      (user["user_id"],)).fetchone()
    con.close()
    if row is None:
        raise HTTPException(status_code=400, detail="user not found")
    try:
        hasher.verify(row["password_hash"], current)
    except (VerifyMismatchError, InvalidHashError):
        raise HTTPException(status_code=400, detail="the current password is wrong") from None
    if len(new) < MIN_PASSWORD:
        raise HTTPException(status_code=400,
                            detail=f"the new password must be {MIN_PASSWORD}+ characters")
    set_password(user["username"], new)


Me = Depends(current_user)
