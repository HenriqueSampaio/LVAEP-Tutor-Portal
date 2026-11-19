#!/usr/bin/env python3
"""Check that the database and email settings in .env work.

    python3 check_setup.py                       # database + email settings
    python3 check_setup.py --send-test you@x.org  # also send one real test email through Resend

Creates the app's tables if they don't exist yet (safe to run on an empty Supabase project).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from app import env

env.load()

from app import db, mailer  # noqa: E402

OK, WARN, FAIL = "✅", "⚠️ ", "❌"
problems = 0


def say(mark, text):
    global problems
    problems += mark == FAIL
    print(f"  {mark} {text}")


def check_database():
    print("\nDatabase")
    if not db.using_postgres():
        say(OK, f"Using the local SQLite file {db.DB_PATH} (set DATABASE_URL to use Supabase).")
        return
    try:
        conn = db.connect()
    except ModuleNotFoundError:
        say(FAIL, "The Postgres driver isn't installed. Run:  python3 -m pip install -r requirements.txt")
        return
    except Exception as e:
        say(FAIL, f"Couldn't connect: {e}")
        say(WARN, "Check the password in DATABASE_URL, and use the Session pooler string from Supabase's Connect button.")
        return
    try:
        version = conn.execute("SHOW server_version").fetchone()[0]
        say(OK, f"Connected to Postgres {version}.")
        db.init(conn)
        mailer.init(conn)
        tables = db.table_names()
        found = {r[0] for r in conn.execute(
            "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'").fetchall()}
        missing = [t for t in tables if t not in found]
        say(FAIL if missing else OK, f"Missing tables: {', '.join(missing)}" if missing else f"All {len(tables)} tables are there.")
        unlocked = [r[0] for r in conn.execute(
            "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' "
            "AND NOT relrowsecurity").fetchall() if r[0] in tables]
        say(FAIL if unlocked else OK, f"Row-level security is OFF for: {', '.join(unlocked)}" if unlocked
            else "Row-level security is on for every table.")
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        say(OK if users else WARN, f"{users} account(s)." if users else
            "No accounts yet — run `python3 server.py --empty` once to create the first staff login.")
    finally:
        conn.close()
    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    if url and key:
        req = urllib.request.Request(f"{url}/rest/v1/users?select=id&limit=1", headers={"apikey": key})
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                rows = json.loads(res.read() or b"[]")
                say(FAIL if rows else OK, "Supabase's public API can read the users table!" if rows
                    else "Supabase's public API sees no rows (tables are locked).")
        except urllib.error.HTTPError as e:
            say(OK, f"Supabase's public API is refused access to the tables (HTTP {e.code}).")
    else:
        say(WARN, "Skipped the public-API check (set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY to run it).")


def check_email(send_to):
    print("\nEmail")
    st = mailer.status()
    if st["mode"] == "off":
        say(WARN, "Email is turned off (EMAIL_MODE=off).")
    elif st["mode"] == "outbox":
        say(WARN, f"No RESEND_API_KEY: emails are saved as files in {st['outbox_dir']} instead of being sent.")
    else:
        say(OK, f"Sending through Resend from: {st['from']}")
        if "resend.dev" in st["from"]:
            say(WARN, "onboarding@resend.dev only delivers to your own Resend account's address. "
                      "Verify LVAEP's domain in Resend and change EMAIL_FROM before inviting tutors.")
    if st["redirect_to"]:
        say(WARN, f"Test mode: EVERY email goes to {st['redirect_to']} (remove EMAIL_REDIRECT_TO for real use).")
    say(OK if not st["app_url"].startswith("http://localhost") else WARN,
        f"Links in emails point to {st['app_url']}" + ("" if not st["app_url"].startswith("http://localhost")
                                                        else " — set APP_URL to the real site address once it's online."))
    if send_to:
        if st["mode"] != "resend":
            say(FAIL, "Can't send a test email without RESEND_API_KEY.")
            return
        body, text = mailer.render("Test email from LVAEP Tutor Hours", ["If you can read this, email is set up correctly."],
                                   "Open LVAEP Tutor Hours", st["app_url"])
        try:
            msg_id = mailer._send_resend(send_to, "", "LVAEP Tutor Hours: test email", body, text)
            say(OK, f"Test email accepted by Resend (id {msg_id}). Check {send_to}'s inbox (and spam).")
        except Exception as e:
            say(FAIL, f"Resend refused the test email: {e}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--send-test", metavar="EMAIL", help="send one real test email to this address")
    args = p.parse_args()
    print("LVAEP Tutor Hours — setup check")
    check_database()
    check_email(args.send_test)
    print("\nAll good!" if not problems else f"\n{problems} problem(s) to fix — see ❌ above.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
