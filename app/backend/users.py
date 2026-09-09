"""Admin CLI for the local accounts. There is no self-signup.

    python users.py add alice                    # prompts for the password
    python users.py passwd alice
    python users.py list
    python users.py disable alice                # revokes every open session

The password is never taken from the command line (it would land in the shell
history) and never printed.
"""
import argparse
import getpass
import sys

import auth
import state


def _ask() -> str:
    first = getpass.getpass("password: ")
    if first != getpass.getpass("again: "):
        raise SystemExit("the two passwords differ")
    if len(first) < auth.MIN_PASSWORD:
        raise SystemExit(f"the password must be {auth.MIN_PASSWORD}+ characters")
    return first


def main() -> None:
    ap = argparse.ArgumentParser(description="Excel Parser accounts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("add", "passwd", "disable"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("list")
    args = ap.parse_args()
    state.init()

    if args.cmd == "add":
        try:
            auth.create_user(args.username, _ask())
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        except Exception as exc:
            raise SystemExit(f"could not create {args.username}: {exc}") from exc
        print(f"created {args.username.strip().lower()}")

    elif args.cmd == "passwd":
        try:
            auth.set_password(args.username, _ask())
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"password changed for {args.username.strip().lower()}")

    elif args.cmd == "disable":
        con = state.connect()
        with con:
            cur = con.execute(
                "UPDATE session SET revoked = 1 WHERE user_id = "
                '(SELECT user_id FROM "user" WHERE username = %s) AND revoked = 0',
                (args.username.strip().lower(),))
            count = cur.rowcount
        con.close()
        print(f"revoked {count} session(s) for {args.username.strip().lower()}")

    else:
        con = state.connect()
        rows = con.execute("SELECT username, created_at, must_change_password "
                           'FROM "user" ORDER BY username').fetchall()
        con.close()
        if not rows:
            print("no users yet - python users.py add <name>")
        for row in rows:
            flag = " (must change password)" if row["must_change_password"] else ""
            print(f"{row['username']:<24} created {row['created_at']}{flag}")


if __name__ == "__main__":
    sys.exit(main())
