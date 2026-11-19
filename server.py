#!/usr/bin/env python3
"""Run the LVAEP tutor reporting prototype.

    python3 server.py              # start on http://127.0.0.1:8070 (seeds demo data on first run)
    python3 server.py --reset      # wipe the database and reload the synthetic demo data
    python3 server.py --empty      # start with an empty database (one staff account, no demo data)
"""
import argparse
import os
import secrets
import sys

from app import env

env.load()  # .env settings must be in place before app.db reads DATABASE_URL

from app import db, mailer, seed  # noqa: E402
from app.server import serve  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                   help="use 0.0.0.0 to open it from a phone on the same Wi-Fi (or on a hosting service)")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8070)))
    p.add_argument("--reset", action="store_true",
                   help="delete the database and reload demo data (on Postgres also needs LVAEP_ALLOW_RESET=1)")
    p.add_argument("--empty", action="store_true", help="with --reset or on first run: no demo data")
    p.add_argument("--demo", action="store_true",
                   help="load the synthetic demo data into an empty Postgres database (SQLite does this by default)")
    args = p.parse_args()

    if args.reset:
        db.reset()
    conn = db.connect()
    db.init(conn)
    mailer.init(conn)
    if db.is_empty(conn):
        mailer.paused = True  # demo data shouldn't queue emails
        if args.empty:
            if db.using_postgres():  # a hosted database may be the live one: no placeholder logins there
                sys.exit("On a Postgres database the first (real) staff login is created with\n"
                         "    python3 bootstrap_admin.py --name 'Full Name' --email person@example.org")
            temp = "-".join(secrets.token_hex(3) for _ in range(3))
            conn.execute(
                "INSERT INTO users (name, email, role, password_hash, must_change_password) VALUES (?, ?, 'staff', ?, 1)",
                ("LVAEP Admin", "admin@lvaep.example", db.hash_password(temp)))
            conn.commit()
            print(f"Empty database created. Sign in as admin@lvaep.example with the temporary password {temp}")
        elif db.using_postgres() and not args.demo:
            # A hosted database may be the live one: never fill it with fake people by accident.
            sys.exit("This Postgres database is empty. To load the synthetic demo data on purpose, run again with "
                     "--demo.\nFor a real site, create the first staff account instead:\n"
                     "    python3 bootstrap_admin.py --name 'Full Name' --email person@example.org")
        else:
            seed.seed(conn)
            print(f"Loaded synthetic demo data (password for every demo account: {seed.DEMO_PASSWORD})")
        mailer.paused = False
    conn.close()
    where = "Postgres (DATABASE_URL)" if db.using_postgres() else db.DB_PATH
    print(f"Database: {where} · Email: {mailer.mode()}"
          + (f" (every email goes to {mailer.redirect_to()})" if mailer.redirect_to() else ""))

    httpd = serve(args.host, args.port)
    print(f"LVAEP tutor reporting running at http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
