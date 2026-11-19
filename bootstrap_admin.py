#!/usr/bin/env python3
"""Create the first staff (admin) account on a database, or give an existing account a new
temporary password. This is how the live site gets its first login: run it once from your
computer with DATABASE_URL pointing at the production database.

    python3 bootstrap_admin.py --name "Cristhian Barcelos" --email cristhian@example.org
    python3 bootstrap_admin.py --email cristhian@example.org --new-password     # lost password

DATABASE_URL is read from the environment or from .env, exactly like server.py. The tables are
created if they don't exist. The script never loads demo data, and refuses to touch a database
that contains the synthetic demo data: the live site must hold real records only.
The temporary password is printed once; the person must choose their own at first sign-in.
"""
import argparse
import secrets
import sys

from app import env

env.load()

from app import db, mailer  # noqa: E402


def temp_password():
    return "-".join(secrets.token_hex(3) for _ in range(3))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--email", required=True, help="the person's sign-in email")
    p.add_argument("--name", help="full name (required when creating the account)")
    p.add_argument("--new-password", action="store_true", help="give an existing account a new temporary password")
    p.add_argument("--allow-demo-data", action="store_true", help="run even if the database holds demo data")
    args = p.parse_args()
    email = args.email.strip()
    if "@" not in email:
        sys.exit("Enter a valid email address.")

    conn = db.connect()
    try:
        db.init(conn)
        mailer.init(conn)
        if db.has_demo_data(conn) and not args.allow_demo_data:
            sys.exit("This database contains the synthetic demo data. The live site must start empty: point\n"
                     "DATABASE_URL at a fresh database (or pass --allow-demo-data if this is only a test).")
        existing = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        temp = temp_password()
        if existing and not args.new_password:
            sys.exit(f"{email} already has an account ({existing['role']}, {'active' if existing['active'] else 'deactivated'}). "
                     "Add --new-password to give it a new temporary password.")
        if existing:
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1, active = 1 WHERE id = ?",
                         (db.hash_password(temp), existing["id"]))
            conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (existing["id"],))
            db.audit(conn, None, "account.reset_password", f"#{existing['id']} {existing['name']} (bootstrap script)")
            name, verb = existing["name"], "Password reset for"
        else:
            if not args.name:
                sys.exit("--name is required when creating an account.")
            name = args.name.strip()
            conn.execute(
                "INSERT INTO users (name, email, role, password_hash, must_change_password) VALUES (?, ?, 'staff', ?, 1)",
                (name, email, db.hash_password(temp)))
            db.audit(conn, None, "account.create", f"staff {name} <{email}> (bootstrap script)")
            verb = "Created staff account for"
        conn.commit()
        counts = {t: conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
                  for t in ("users", "students", "assignments", "sessions")}
    finally:
        conn.close()

    where = "Postgres (DATABASE_URL)" if db.using_postgres() else f"SQLite file {db.DB_PATH}"
    print(f"Database: {where}")
    print("Records: " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    print(f"\n{verb} {name} <{email}>.")
    print("Temporary password (shown once; they choose their own at first sign-in):\n")
    print(f"    {temp}\n")


if __name__ == "__main__":
    main()
