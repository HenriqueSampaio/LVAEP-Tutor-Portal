"""Tutor reminders: month-end, overdue and (optional) weekly nudges.

Reminders are delivered in-app. Each notification row carries an email_status so an
email provider can be plugged in later without changing the reminder rules.
"""
import datetime as dt

from . import db


def _already_ran(conn, kind, period_key):
    return conn.execute(
        "SELECT 1 FROM reminder_runs WHERE kind = ? AND period_key = ? AND triggered_by IS NULL",
        (kind, period_key),
    ).fetchone() is not None


def tutors_missing_report(conn, month):
    """Tutors with at least one assigned student whose report for `month` is not submitted."""
    missing = {}
    for a in db.active_assignments(conn, month):
        if a["student_status"] == "dropped" and a["end_date"] and a["end_date"] < db.month_bounds(month)[0].isoformat():
            continue
        report = db.get_report(conn, a["tutor_id"], a["student_id"], month)
        if report is None or report["status"] == "draft":
            missing.setdefault(a["tutor_id"], []).append(a["student_name"])
    return missing


def send_month_reminders(conn, month, kind, triggered_by=None):
    label = db.month_bounds(month)[0].strftime("%B")
    missing = tutors_missing_report(conn, month)
    for tutor_id, students in missing.items():
        names = ", ".join(students)
        if kind == "overdue":
            msg = f"Your {label} hours are overdue. Please submit the month for: {names}."
        elif kind == "manual":
            msg = f"Reminder from LVAEP staff: please submit your {label} hours for: {names}."
        else:
            msg = f"It's the last day of {label} — don't forget to submit your hours for: {names}."
        db.notify(conn, tutor_id, kind, msg, link=f"#/tutor?month={month}")
    conn.execute(
        "INSERT INTO reminder_runs (kind, period_key, recipients, triggered_by) VALUES (?, ?, ?, ?)",
        (kind, month, len(missing), triggered_by),
    )
    return len(missing)


def send_weekly_reminders(conn, today):
    since = (today - dt.timedelta(days=7)).isoformat()
    month = today.strftime("%Y-%m")
    count = 0
    tutors = {a["tutor_id"] for a in db.active_assignments(conn, month) if a["end_date"] is None}
    for tutor_id in tutors:
        logged = conn.execute(
            "SELECT 1 FROM sessions WHERE tutor_id = ? AND date > ?", (tutor_id, since)
        ).fetchone()
        if not logged:
            db.notify(conn, tutor_id, "weekly",
                      "You haven't logged any sessions this week. Add this week's hours when you have a minute.",
                      link=f"#/tutor?month={month}")
            count += 1
    iso = today.isocalendar()
    conn.execute(
        "INSERT INTO reminder_runs (kind, period_key, recipients) VALUES ('weekly', ?, ?)",
        (f"{iso[0]}-W{iso[1]:02d}", count),
    )
    return count


def run_scheduled(conn, today=None):
    """Idempotent: safe to call as often as you like; each reminder fires once per period."""
    today = today or db.today()
    sent = []
    month = today.strftime("%Y-%m")
    _, last = db.month_bounds(month)
    if db.setting(conn, "reminder_month_end") == "1" and today == last and not _already_ran(conn, "month_end", month):
        sent.append(("month_end", send_month_reminders(conn, month, "month_end")))
    prev = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    if db.setting(conn, "reminder_overdue") == "1" and today.day >= 3 and not _already_ran(conn, "overdue", prev):
        sent.append(("overdue", send_month_reminders(conn, prev, "overdue")))
    iso = today.isocalendar()
    week_key = f"{iso[0]}-W{iso[1]:02d}"
    if (db.setting(conn, "reminder_weekly") == "1"
            and today.weekday() == int(db.setting(conn, "reminder_weekly_day"))
            and not _already_ran(conn, "weekly", week_key)):
        sent.append(("weekly", send_weekly_reminders(conn, today)))
    conn.commit()
    return sent
