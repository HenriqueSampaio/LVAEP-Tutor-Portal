"""Database schema, connection helpers and shared domain rules for the LVAEP prototype."""
import calendar
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import sqlite3

DB_PATH = os.environ.get("LVAEP_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "lvaep.sqlite3"))

ATTENDANCE_CODES = {
    "present": "Present",
    "student_absent": "Student absent",
    "tutor_absent": "Tutor absent",
    "holiday": "Holiday / site closed",
    "cancelled": "Cancelled",
}

# Placeholder list — the client's form defines the real achievement fields (PRD open decision).
ACHIEVEMENTS = [
    "Read a book, newspaper or article independently",
    "Wrote a letter, email or text message",
    "Filled out a form or application",
    "Got a library card",
    "Read to a child / helped with homework",
    "Used a computer, phone or the internet for a new task",
    "Got a job or a better job",
    "Passed a test (citizenship, driver's, HSE, etc.)",
    "Opened a bank account / managed a budget",
    "Registered to vote / voted",
    "Spoke with a doctor, teacher or landlord without help",
]

WEEKLY_TARGET_HOURS = 4.0  # 2 h tutoring + 2 h homework per week (client meeting notes)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT,
    role TEXT NOT NULL CHECK (role IN ('tutor', 'staff')),
    password_hash TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    training_hours REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    program TEXT NOT NULL DEFAULT 'ESL',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'dropped')),
    enrolled_on TEXT NOT NULL,
    left_on TEXT,
    leave_reason TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY,
    tutor_id INTEGER NOT NULL REFERENCES users(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    meeting_place TEXT NOT NULL DEFAULT '',
    schedule TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL,
    end_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    tutor_id INTEGER NOT NULL REFERENCES users(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    date TEXT NOT NULL,
    attendance TEXT NOT NULL DEFAULT 'present',
    tutoring_hours REAL NOT NULL DEFAULT 0,
    homework_hours REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (tutor_id, student_id, date)
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    tutor_id INTEGER NOT NULL REFERENCES users(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    month TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'reviewed')),
    achievements TEXT NOT NULL DEFAULT '[]',
    achievement_notes TEXT NOT NULL DEFAULT '',
    leaving_date TEXT,
    leaving_reason TEXT NOT NULL DEFAULT '',
    submitted_at TEXT,
    reviewed_at TEXT,
    reviewed_by INTEGER REFERENCES users(id),
    returned INTEGER NOT NULL DEFAULT 0,
    staff_note TEXT NOT NULL DEFAULT '',
    UNIQUE (tutor_id, student_id, month)
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    email_status TEXT NOT NULL DEFAULT 'not_configured',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    read_at TEXT
);
CREATE TABLE IF NOT EXISTS reminder_runs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    period_key TEXT NOT NULL,
    recipients INTEGER NOT NULL,
    triggered_by INTEGER REFERENCES users(id),
    ran_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_sessions_pair ON sessions (tutor_id, student_id, date);
CREATE INDEX IF NOT EXISTS idx_assign_tutor ON assignments (tutor_id);
CREATE INDEX IF NOT EXISTS idx_assign_student ON assignments (student_id);
"""

DEFAULT_SETTINGS = {
    "reminder_month_end": "1",   # remind on the last day of the month
    "reminder_overdue": "1",     # remind on the 3rd for last month's missing reports
    "reminder_weekly": "0",      # weekly nudge when nothing was logged in 7 days
    "reminder_weekly_day": "4",  # 0 = Monday ... 4 = Friday
}


def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init(conn):
    conn.executescript(SCHEMA)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()


# ---------- time ----------

def today():
    """Today's date; LVAEP_TODAY=YYYY-MM-DD overrides it for demos and tests."""
    override = os.environ.get("LVAEP_TODAY")
    return dt.date.fromisoformat(override) if override else dt.date.today()


def now_iso():
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def month_bounds(month):
    year, mon = (int(x) for x in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    return dt.date(year, mon, 1), dt.date(year, mon, last)


def valid_month(month):
    try:
        month_bounds(month)
        return len(month) == 7
    except (ValueError, AttributeError):
        return False


def fiscal_year_start(month):
    """LVAEP's fiscal year is assumed to run July 1 – June 30 (form is 'FY 2026–2027')."""
    year, mon = (int(x) for x in month.split("-"))
    return dt.date(year if mon >= 7 else year - 1, 7, 1)


def fiscal_year_label(month):
    start = fiscal_year_start(month)
    return f"FY {start.year}–{start.year + 1}"


def fiscal_months(month):
    start = fiscal_year_start(month)
    out = []
    for i in range(12):
        y, m = start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def weeks_in_month(month):
    first, last = month_bounds(month)
    return round(((last - first).days + 1) / 7, 1)


# ---------- passwords ----------

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"pbkdf2${salt}${digest}"


def check_password(password, stored):
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt).split("$")[2], digest)


# ---------- shared queries ----------

def audit(conn, user_id, action, detail=""):
    conn.execute("INSERT INTO audit_log (user_id, action, detail) VALUES (?, ?, ?)", (user_id, action, detail))


def notify(conn, user_id, kind, message, link=""):
    conn.execute(
        "INSERT INTO notifications (user_id, kind, message, link) VALUES (?, ?, ?, ?)",
        (user_id, kind, message, link),
    )


def setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS.get(key)


def active_assignments(conn, month, tutor_id=None):
    """Assignments that overlap the given month (a pair stays visible for the month it ended in)."""
    first, last = month_bounds(month)
    sql = """
        SELECT a.*, u.name AS tutor_name, u.email AS tutor_email,
               s.first_name || ' ' || s.last_name AS student_name, s.status AS student_status, s.program
        FROM assignments a
        JOIN users u ON u.id = a.tutor_id
        JOIN students s ON s.id = a.student_id
        WHERE a.start_date <= ? AND (a.end_date IS NULL OR a.end_date >= ?)
    """
    args = [last.isoformat(), first.isoformat()]
    if tutor_id is not None:
        sql += " AND a.tutor_id = ?"
        args.append(tutor_id)
    sql += " ORDER BY u.name, s.last_name, s.first_name"
    return conn.execute(sql, args).fetchall()


def tutor_has_student(conn, tutor_id, student_id):
    return conn.execute(
        "SELECT 1 FROM assignments WHERE tutor_id = ? AND student_id = ?", (tutor_id, student_id)
    ).fetchone() is not None


def assignment_for(conn, tutor_id, student_id, month=None):
    rows = conn.execute(
        "SELECT * FROM assignments WHERE tutor_id = ? AND student_id = ? ORDER BY start_date DESC",
        (tutor_id, student_id),
    ).fetchall()
    if month:
        first, last = month_bounds(month)
        for r in rows:
            if r["start_date"] <= last.isoformat() and (r["end_date"] is None or r["end_date"] >= first.isoformat()):
                return r
    return rows[0] if rows else None


def get_report(conn, tutor_id, student_id, month):
    return conn.execute(
        "SELECT * FROM reports WHERE tutor_id = ? AND student_id = ? AND month = ?", (tutor_id, student_id, month)
    ).fetchone()


def ensure_report(conn, tutor_id, student_id, month):
    conn.execute(
        "INSERT OR IGNORE INTO reports (tutor_id, student_id, month) VALUES (?, ?, ?)", (tutor_id, student_id, month)
    )
    return get_report(conn, tutor_id, student_id, month)


def month_sessions(conn, tutor_id, student_id, month):
    first, last = month_bounds(month)
    return conn.execute(
        """SELECT * FROM sessions WHERE tutor_id = ? AND student_id = ? AND date BETWEEN ? AND ?
           ORDER BY date""",
        (tutor_id, student_id, first.isoformat(), last.isoformat()),
    ).fetchall()


def hour_totals(conn, where, args):
    row = conn.execute(
        f"""SELECT COUNT(*) AS entries,
                   SUM(CASE WHEN attendance = 'present' THEN 1 ELSE 0 END) AS attended,
                   COALESCE(SUM(tutoring_hours), 0) AS tutoring,
                   COALESCE(SUM(homework_hours), 0) AS homework
            FROM sessions WHERE {where}""",
        args,
    ).fetchone()
    tut, hw = round(row["tutoring"], 2), round(row["homework"], 2)
    return {"entries": row["entries"], "attended": row["attended"] or 0,
            "tutoring": tut, "homework": hw, "total": round(tut + hw, 2)}


def report_status(report, sessions_count):
    if report is None or report["status"] == "draft":
        if report is not None and report["returned"]:
            return "returned"
        return "in_progress" if sessions_count else "not_started"
    return report["status"]


def fiscal_breakdown(conn, tutor_id, student_id, month):
    """Per-month hours from the start of the fiscal year through `month` (what the PDF form totals)."""
    months = fiscal_months(month)
    rows = []
    for m in months:
        first, last = month_bounds(m)
        t = hour_totals(
            conn, "tutor_id = ? AND student_id = ? AND date BETWEEN ? AND ?",
            (tutor_id, student_id, first.isoformat(), last.isoformat()),
        )
        rows.append({"month": m, "future": m > month, **t})
    upto = [r for r in rows if not r["future"]]
    totals = {k: round(sum(r[k] for r in upto), 2) for k in ("tutoring", "homework", "total")}
    totals["attended"] = sum(r["attended"] for r in upto)
    return {"label": fiscal_year_label(month), "months": rows, "totals": totals}


def report_bundle(conn, tutor_id, student_id, month):
    """Everything needed to show, review or print one tutor–student monthly report."""
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    tutor = conn.execute("SELECT id, name, email, phone FROM users WHERE id = ?", (tutor_id,)).fetchone()
    assignment = assignment_for(conn, tutor_id, student_id, month)
    report = get_report(conn, tutor_id, student_id, month)
    sessions = month_sessions(conn, tutor_id, student_id, month)
    first, last = month_bounds(month)
    totals = hour_totals(
        conn, "tutor_id = ? AND student_id = ? AND date BETWEEN ? AND ?",
        (tutor_id, student_id, first.isoformat(), last.isoformat()),
    )
    co_tutors = conn.execute(
        """SELECT DISTINCT u.name FROM assignments a JOIN users u ON u.id = a.tutor_id
           WHERE a.student_id = ? AND a.tutor_id != ? AND a.start_date <= ?
             AND (a.end_date IS NULL OR a.end_date >= ?)""",
        (student_id, tutor_id, last.isoformat(), first.isoformat()),
    ).fetchall()
    reviewer = None
    if report and report["reviewed_by"]:
        r = conn.execute("SELECT name FROM users WHERE id = ?", (report["reviewed_by"],)).fetchone()
        reviewer = r["name"] if r else None
    return {
        "month": month,
        "month_label": first.strftime("%B %Y"),
        "fiscal_year": fiscal_year_label(month),
        "student": {
            "id": student["id"], "name": f"{student['first_name']} {student['last_name']}",
            "first_name": student["first_name"], "last_name": student["last_name"],
            "program": student["program"], "status": student["status"],
            "enrolled_on": student["enrolled_on"], "left_on": student["left_on"],
        },
        "tutor": dict(tutor),
        "co_tutors": [r["name"] for r in co_tutors],
        "assignment": dict(assignment) if assignment else None,
        "sessions": [dict(s) for s in sessions],
        "totals": totals,
        "weekly_target": WEEKLY_TARGET_HOURS,
        "target_hours": round(WEEKLY_TARGET_HOURS * weeks_in_month(month)),
        "fiscal": fiscal_breakdown(conn, tutor_id, student_id, month),
        "report": {
            "status": report_status(report, len(sessions)),
            "achievements": json.loads(report["achievements"]) if report else [],
            "achievement_notes": report["achievement_notes"] if report else "",
            "leaving_date": report["leaving_date"] if report else None,
            "leaving_reason": report["leaving_reason"] if report else "",
            "submitted_at": report["submitted_at"] if report else None,
            "reviewed_at": report["reviewed_at"] if report else None,
            "reviewed_by": reviewer,
            "staff_note": report["staff_note"] if report else "",
            "locked": bool(report and report["status"] != "draft"),
        },
        "month_closed": last < today(),
    }
