"""HTTP server and JSON API for the LVAEP tutor reporting prototype (Python stdlib only)."""
import datetime as dt
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import traceback
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import db, exports, reminders

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
TOKEN_DAYS = 14
COOKIE = "lvaep_session"


class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


class Raw:
    def __init__(self, body, content_type, filename=None):
        self.body, self.content_type, self.filename = body, content_type, filename


ROUTES = []


def route(method, pattern, role=None, auth=True):
    def wrap(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn, role, auth))
        return fn
    return wrap


class Ctx:
    def __init__(self, conn, user, params, query, body):
        self.conn, self.user, self.params, self.query, self.body = conn, user, params, query, body

    def q(self, key, default=None):
        return self.query.get(key, [default])[0]

    def month(self):
        month = self.q("month") or db.today().strftime("%Y-%m")
        if not db.valid_month(month):
            raise ApiError(400, "Month must look like YYYY-MM.")
        return month

    @property
    def is_staff(self):
        return self.user["role"] == "staff"


# ---------- helpers ----------

def need(body, *keys):
    missing = [k for k in keys if body.get(k) in (None, "")]
    if missing:
        raise ApiError(400, f"Missing required field(s): {', '.join(missing)}.")


def parse_date(value, field="date"):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"'{field}' must be a valid date (YYYY-MM-DD).")


def parse_hours(value, field):
    try:
        h = float(value or 0)
    except (TypeError, ValueError):
        raise ApiError(400, f"{field} must be a number.")
    if h < 0 or h > 8:
        raise ApiError(400, f"{field} must be between 0 and 8.")
    if round(h * 4) != h * 4:
        raise ApiError(400, f"{field} must be in quarter hours (e.g. 1.5 or 1.75).")
    return h


def user_public(u):
    return {k: u[k] for k in ("id", "name", "email", "phone", "role", "must_change_password", "active",
                              "training_hours")}


def check_pair_access(ctx, tutor_id, student_id):
    """Assignment-based access: tutors only see their own students; staff see everything."""
    if ctx.is_staff:
        if not ctx.conn.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone():
            raise ApiError(404, "Student not found.")
        return
    if tutor_id != ctx.user["id"] or not db.tutor_has_student(ctx.conn, tutor_id, student_id):
        raise ApiError(403, "You are not assigned to this student.")


def check_editable(ctx, tutor_id, student_id, month):
    report = db.get_report(ctx.conn, tutor_id, student_id, month)
    if report and report["status"] != "draft" and not ctx.is_staff:
        raise ApiError(409, "This month has already been submitted. Ask LVAEP staff to reopen it if something needs to change.")


def names(conn, tutor_id, student_id):
    t = conn.execute("SELECT name FROM users WHERE id = ?", (tutor_id,)).fetchone()
    s = conn.execute("SELECT first_name || ' ' || last_name AS n FROM students WHERE id = ?", (student_id,)).fetchone()
    return (t["name"] if t else "?"), (s["n"] if s else "?")


def staff_ids(conn):
    return [r["id"] for r in conn.execute("SELECT id FROM users WHERE role = 'staff' AND active = 1")]


# ---------- auth ----------

@route("POST", "/api/login", auth=False)
def login(ctx):
    need(ctx.body, "email", "password")
    u = ctx.conn.execute("SELECT * FROM users WHERE email = ?", (ctx.body["email"].strip(),)).fetchone()
    if not u or not db.check_password(ctx.body["password"], u["password_hash"]):
        raise ApiError(401, "That email and password don't match an account.")
    if not u["active"]:
        raise ApiError(403, "This account has been deactivated. Contact LVAEP staff.")
    token = secrets.token_urlsafe(32)
    expires = (dt.datetime.now() + dt.timedelta(days=TOKEN_DAYS)).isoformat()
    ctx.conn.execute("INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (?, ?, ?)", (token, u["id"], expires))
    ctx.conn.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (dt.datetime.now().isoformat(),))
    ctx.set_cookie = token
    return {"user": user_public(u)}


@route("POST", "/api/logout")
def logout(ctx):
    ctx.conn.execute("DELETE FROM auth_tokens WHERE token = ?", (ctx.token,))
    ctx.set_cookie = ""
    return {"ok": True}


@route("GET", "/api/me")
def me(ctx):
    unread = ctx.conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND read_at IS NULL", (ctx.user["id"],)
    ).fetchone()["c"]
    pending = 0
    if not ctx.is_staff:
        pending = ctx.conn.execute(
            "SELECT COUNT(*) AS c FROM calendar_events WHERE tutor_id = ? AND status = 'pending'", (ctx.user["id"],)
        ).fetchone()["c"]
    return {"user": user_public(ctx.user), "unread": unread, "pending_requests": pending}


@route("POST", "/api/me/password")
def change_password(ctx):
    need(ctx.body, "current", "new")
    if not db.check_password(ctx.body["current"], ctx.user["password_hash"]):
        raise ApiError(400, "Your current password is incorrect.")
    if len(ctx.body["new"]) < 8:
        raise ApiError(400, "Choose a password with at least 8 characters.")
    ctx.conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                     (db.hash_password(ctx.body["new"]), ctx.user["id"]))
    return {"ok": True}


@route("GET", "/api/meta", auth=False)
def meta(ctx):
    return {"attendance": db.ATTENDANCE_CODES, "achievements": db.ACHIEVEMENTS,
            "achievement_groups": [{"heading": h, "items": items} for h, items in db.ACHIEVEMENT_GROUPS],
            "today": db.today().isoformat(), "weekly_target": db.WEEKLY_TARGET_HOURS}


# ---------- notifications ----------

@route("GET", "/api/notifications")
def notifications(ctx):
    rows = ctx.conn.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 30", (ctx.user["id"],)
    ).fetchall()
    return {"items": [dict(r) for r in rows]}


@route("POST", "/api/notifications/read")
def notifications_read(ctx):
    ctx.conn.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                     (db.now_iso(), ctx.user["id"]))
    return {"ok": True}


# ---------- tutor ----------

@route("GET", "/api/tutor/home", role="tutor")
def tutor_home(ctx):
    month = ctx.month()
    rows = []
    for a in db.active_assignments(ctx.conn, month, ctx.user["id"]):
        b = db.report_bundle(ctx.conn, a["tutor_id"], a["student_id"], month)
        last = ctx.conn.execute(
            "SELECT MAX(date) AS d FROM sessions WHERE tutor_id = ? AND student_id = ?",
            (a["tutor_id"], a["student_id"])).fetchone()["d"]
        rows.append({"student_id": a["student_id"], "student_name": a["student_name"], "program": a["program"],
                     "student_status": a["student_status"], "meeting_place": a["meeting_place"],
                     "schedule": a["schedule"], "end_date": a["end_date"], "status": b["report"]["status"],
                     "totals": b["totals"], "target_hours": b["target_hours"], "last_session": last,
                     "staff_note": b["report"]["staff_note"], "co_tutors": b["co_tutors"]})
    today = db.today()
    _, last_day = db.month_bounds(month)
    # Earlier months this tutor still owes.
    overdue = []
    for m in [(today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")]:
        missing = reminders.tutors_missing_report(ctx.conn, m).get(ctx.user["id"])
        if missing:
            overdue.append({"month": m, "label": db.month_bounds(m)[0].strftime("%B %Y"), "students": missing})
    return {"month": month, "month_label": db.month_bounds(month)[0].strftime("%B %Y"),
            "students": rows, "days_left": (last_day - today).days, "overdue": overdue,
            "is_current": month == today.strftime("%Y-%m")}


# ---------- reports (shared by tutors and staff) ----------

REPORT = r"/api/reports/(?P<tutor_id>\d+)/(?P<student_id>\d+)/(?P<month>\d{4}-\d{2})"


def _report_ids(ctx):
    tutor_id, student_id, month = int(ctx.params["tutor_id"]), int(ctx.params["student_id"]), ctx.params["month"]
    if not db.valid_month(month):
        raise ApiError(400, "Invalid month.")
    check_pair_access(ctx, tutor_id, student_id)
    return tutor_id, student_id, month


@route("GET", REPORT)
def report_get(ctx):
    tutor_id, student_id, month = _report_ids(ctx)
    return db.report_bundle(ctx.conn, tutor_id, student_id, month)


@route("PUT", REPORT)
def report_save(ctx):
    tutor_id, student_id, month = _report_ids(ctx)
    check_editable(ctx, tutor_id, student_id, month)
    b = ctx.body
    achievements = [str(x)[:200] for x in (b.get("achievements") or [])][:30]
    leaving_date = b.get("leaving_date") or None
    if leaving_date:
        parse_date(leaving_date, "leaving_date")
    db.ensure_report(ctx.conn, tutor_id, student_id, month)
    ctx.conn.execute(
        """UPDATE reports SET achievements = ?, achievement_notes = ?, achievement_other = ?, leaving_date = ?,
           leaving_reason = ? WHERE tutor_id = ? AND student_id = ? AND month = ?""",
        (json.dumps(achievements), (b.get("achievement_notes") or "")[:2000], (b.get("achievement_other") or "")[:300],
         leaving_date,
         (b.get("leaving_reason") or "")[:500], tutor_id, student_id, month))
    if ctx.is_staff:
        t, s = names(ctx.conn, tutor_id, student_id)
        db.audit(ctx.conn, ctx.user["id"], "report.edit", f"{t} / {s} / {month}: achievements & leaving info")
    return db.report_bundle(ctx.conn, tutor_id, student_id, month)


@route("POST", REPORT + "/submit")
def report_submit(ctx):
    tutor_id, student_id, month = _report_ids(ctx)
    report = db.ensure_report(ctx.conn, tutor_id, student_id, month)
    if report["status"] != "draft":
        raise ApiError(409, "This month was already submitted.")
    first, _ = db.month_bounds(month)
    if first > db.today():
        raise ApiError(400, "You can't submit a month that hasn't started yet.")
    if not db.month_sessions(ctx.conn, tutor_id, student_id, month):
        raise ApiError(400, "Add at least one session (or an absence/holiday entry) before submitting.")
    ctx.conn.execute(
        """UPDATE reports SET status = 'submitted', submitted_at = ?, returned = 0
           WHERE tutor_id = ? AND student_id = ? AND month = ?""", (db.now_iso(), tutor_id, student_id, month))
    t, s = names(ctx.conn, tutor_id, student_id)
    who = "Staff (on tutor's behalf)" if ctx.is_staff else t
    db.audit(ctx.conn, ctx.user["id"], "report.submit", f"{t} / {s} / {month} submitted by {who}")
    report = db.get_report(ctx.conn, tutor_id, student_id, month)
    if report["leaving_date"] or report["leaving_reason"]:
        for sid in staff_ids(ctx.conn):
            db.notify(ctx.conn, sid, "leaving",
                      f"{t} reports that {s} stopped tutoring ({report['leaving_date'] or 'date not given'}): "
                      f"{report['leaving_reason'] or 'no reason given'}. Review the student's status.",
                      link=f"#/staff/report/{tutor_id}/{student_id}/{month}")
    return db.report_bundle(ctx.conn, tutor_id, student_id, month)


@route("POST", REPORT + "/review", role="staff")
def report_review(ctx):
    tutor_id, student_id, month = _report_ids(ctx)
    report = db.get_report(ctx.conn, tutor_id, student_id, month)
    if not report or report["status"] != "submitted":
        raise ApiError(409, "Only submitted reports can be marked reviewed.")
    ctx.conn.execute(
        "UPDATE reports SET status = 'reviewed', reviewed_at = ?, reviewed_by = ? WHERE id = ?",
        (db.now_iso(), ctx.user["id"], report["id"]))
    t, s = names(ctx.conn, tutor_id, student_id)
    db.audit(ctx.conn, ctx.user["id"], "report.review", f"{t} / {s} / {month}")
    return db.report_bundle(ctx.conn, tutor_id, student_id, month)


@route("POST", REPORT + "/return", role="staff")
def report_return(ctx):
    tutor_id, student_id, month = _report_ids(ctx)
    need(ctx.body, "note")
    report = db.get_report(ctx.conn, tutor_id, student_id, month)
    if not report or report["status"] == "draft":
        raise ApiError(409, "Only submitted or reviewed reports can be returned.")
    ctx.conn.execute(
        """UPDATE reports SET status = 'draft', returned = 1, staff_note = ?, reviewed_at = NULL, reviewed_by = NULL
           WHERE id = ?""", (ctx.body["note"][:1000], report["id"]))
    t, s = names(ctx.conn, tutor_id, student_id)
    label = db.month_bounds(month)[0].strftime("%B")
    db.notify(ctx.conn, tutor_id, "returned",
              f"Staff reopened your {label} report for {s}: “{ctx.body['note'][:200]}” Please fix it and submit again.",
              link=f"#/tutor/student/{student_id}?month={month}")
    db.audit(ctx.conn, ctx.user["id"], "report.return", f"{t} / {s} / {month}: {ctx.body['note'][:200]}")
    return db.report_bundle(ctx.conn, tutor_id, student_id, month)


# ---------- sessions ----------

def _validate_session(ctx, body, tutor_id, student_id, existing_id=None):
    need(body, "date", "attendance")
    date = parse_date(body["date"])
    if date > db.today():
        raise ApiError(400, "Sessions can't be logged for a future date.")
    attendance = body["attendance"]
    if attendance not in db.ATTENDANCE_CODES:
        raise ApiError(400, "Unknown attendance code.")
    tut = parse_hours(body.get("tutoring_hours"), "Tutoring hours")
    hw = parse_hours(body.get("homework_hours"), "Homework hours")
    if attendance != "present":
        tut = hw = 0.0
    elif tut + hw <= 0:
        raise ApiError(400, "Enter tutoring or homework hours for a session the student attended.")
    if not db.assignment_covers(ctx.conn, tutor_id, student_id, date.isoformat()):
        raise ApiError(400, "That date is outside this tutor's assignment period for the student.")
    dup = ctx.conn.execute(
        "SELECT id FROM sessions WHERE tutor_id = ? AND student_id = ? AND date = ? AND id != ?",
        (tutor_id, student_id, date.isoformat(), existing_id or 0)).fetchone()
    if dup:
        raise ApiError(409, "A session is already logged on this date. Edit that entry instead.", session_id=dup["id"])
    check_editable(ctx, tutor_id, student_id, date.strftime("%Y-%m"))
    return date.isoformat(), attendance, tut, hw, (body.get("note") or "")[:500]


def _session_audit(ctx, action, tutor_id, student_id, date):
    if ctx.is_staff:
        t, s = names(ctx.conn, tutor_id, student_id)
        db.audit(ctx.conn, ctx.user["id"], action, f"{t} / {s} / {date}")


@route("POST", "/api/sessions")
def session_create(ctx):
    need(ctx.body, "student_id")
    student_id = int(ctx.body["student_id"])
    tutor_id = int(ctx.body.get("tutor_id") or 0) if ctx.is_staff else ctx.user["id"]
    if not tutor_id:
        raise ApiError(400, "Staff must say which tutor the session belongs to.")
    check_pair_access(ctx, tutor_id, student_id)
    date, att, tut, hw, note = _validate_session(ctx, ctx.body, tutor_id, student_id)
    cur = ctx.conn.execute(
        """INSERT INTO sessions (tutor_id, student_id, date, attendance, tutoring_hours, homework_hours, note, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (tutor_id, student_id, date, att, tut, hw, note, ctx.user["id"]))
    db.ensure_report(ctx.conn, tutor_id, student_id, date[:7])
    _session_audit(ctx, "session.add", tutor_id, student_id, date)
    return {"id": cur.lastrowid}


def _load_session(ctx):
    s = ctx.conn.execute("SELECT * FROM sessions WHERE id = ?", (int(ctx.params["id"]),)).fetchone()
    if not s:
        raise ApiError(404, "Session not found.")
    check_pair_access(ctx, s["tutor_id"], s["student_id"])
    check_editable(ctx, s["tutor_id"], s["student_id"], s["date"][:7])
    return s


@route("PUT", r"/api/sessions/(?P<id>\d+)")
def session_update(ctx):
    s = _load_session(ctx)
    date, att, tut, hw, note = _validate_session(ctx, ctx.body, s["tutor_id"], s["student_id"], s["id"])
    ctx.conn.execute(
        """UPDATE sessions SET date = ?, attendance = ?, tutoring_hours = ?, homework_hours = ?, note = ?, updated_at = ?
           WHERE id = ?""", (date, att, tut, hw, note, db.now_iso(), s["id"]))
    _session_audit(ctx, "session.edit", s["tutor_id"], s["student_id"], date)
    return {"ok": True}


@route("DELETE", r"/api/sessions/(?P<id>\d+)")
def session_delete(ctx):
    s = _load_session(ctx)
    ctx.conn.execute("DELETE FROM sessions WHERE id = ?", (s["id"],))
    _session_audit(ctx, "session.delete", s["tutor_id"], s["student_id"], s["date"])
    return {"ok": True}


# ---------- calendar (scheduled sessions) ----------

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
CALENDAR_MAX_DAYS = 62


def clock(t):
    """'18:30' -> '6:30 PM'."""
    h, m = (int(x) for x in t.split(":"))
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def event_label(ev):
    students = ", ".join(s["name"] for s in ev["students"]) or "no students"
    d = dt.date.fromisoformat(ev["date"])
    when = f"{d:%a %b} {d.day}"
    return f"{students} on {when}, {clock(ev['start_time'])}–{clock(ev['end_time'])}"


def event_link(ev, staff=False):
    link = f"#/calendar?view=week&date={ev['date']}&event={ev['id']}"
    return link + f"&tutor={ev['tutor_id']}" if staff else link


def check_event_access(ctx):
    """Load the event in the URL. Tutors only reach events on their own calendar; staff reach all."""
    ev = db.calendar_event(ctx.conn, int(ctx.params["id"]))
    if not ev:
        raise ApiError(404, "Session not found.")
    if not ctx.is_staff and ev["tutor_id"] != ctx.user["id"]:
        raise ApiError(403, "This session isn't on your calendar.")
    return ev


def event_actions(ctx, ev):
    """What the signed-in user may do with an event (the UI shows exactly these buttons)."""
    status, acts = ev["status"], []
    if ctx.is_staff:
        if status == "pending" and ev["created_by"] == ctx.user["id"]:
            acts += ["edit", "cancel"]
        elif status in ("pending", "confirmed"):
            acts.append("cancel")
    elif ev["tutor_id"] == ctx.user["id"]:
        if status == "pending":
            acts += ["approve", "reject"]
        elif status == "confirmed":
            acts += ["edit", "cancel"]
            if ev["date"] <= db.today().isoformat():
                acts.append("log_hours")
    return acts


def with_actions(ctx, events):
    return [{**ev, "actions": event_actions(ctx, ev)} for ev in events]


def _calendar_tutor(ctx, raw, allow_all=False):
    """Which tutor's calendar a request is about. Tutors can only ever name themselves."""
    if not ctx.is_staff:
        if raw not in (None, "", str(ctx.user["id"]), ctx.user["id"]):
            raise ApiError(403, "You can only use your own calendar.")
        return ctx.user["id"]
    if allow_all and raw == "all":
        return None
    try:
        tutor_id = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, "Choose a tutor.")
    t = ctx.conn.execute("SELECT * FROM users WHERE id = ? AND role = 'tutor'", (tutor_id,)).fetchone()
    if not t:
        raise ApiError(404, "Tutor not found.")
    return tutor_id


def _validate_event(ctx, body, tutor_id, existing_id=0):
    need(body, "date", "start_time", "end_time")
    date = parse_date(body["date"])
    start, end = str(body["start_time"]), str(body["end_time"])
    if not TIME_RE.match(start) or not TIME_RE.match(end):
        raise ApiError(400, "Times must look like HH:MM (24-hour).")
    if end <= start:
        raise ApiError(400, "The end time must be after the start time.")
    raw_ids = body.get("student_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ApiError(400, "Choose at least one student.")
    try:
        student_ids = sorted({int(x) for x in raw_ids})
    except (TypeError, ValueError):
        raise ApiError(400, "Student ids must be numbers.")
    for sid in student_ids:
        s = ctx.conn.execute("SELECT first_name || ' ' || last_name AS n FROM students WHERE id = ?", (sid,)).fetchone()
        if not s:
            raise ApiError(404, "Student not found.")
        if not db.assignment_covers(ctx.conn, tutor_id, sid, date.isoformat()):
            raise ApiError(400, f"{s['n']} isn't assigned to this tutor on {date:%b} {date.day}.")
    if ctx.is_staff:
        tutor = ctx.conn.execute("SELECT active FROM users WHERE id = ?", (tutor_id,)).fetchone()
        if not tutor["active"]:
            raise ApiError(400, "That tutor's account is deactivated.")
        if date < db.today():
            raise ApiError(400, "Staff can't propose sessions on a past date.")
    clash = db.confirmed_overlap(ctx.conn, tutor_id, date.isoformat(), start, end, existing_id)
    if clash:
        raise ApiError(409, f"This overlaps a confirmed session ({event_label(clash)}).", conflict_id=clash["id"])
    return {"date": date.isoformat(), "start_time": start, "end_time": end, "student_ids": student_ids,
            "notes": (body.get("notes") or "")[:1000]}


def _save_students(conn, event_id, student_ids):
    conn.execute("DELETE FROM calendar_event_students WHERE event_id = ?", (event_id,))
    conn.executemany("INSERT INTO calendar_event_students (event_id, student_id) VALUES (?, ?)",
                     [(event_id, sid) for sid in student_ids])


@route("GET", "/api/calendar")
def calendar_get(ctx):
    start, end = parse_date(ctx.q("start"), "start"), parse_date(ctx.q("end"), "end")
    if end < start:
        raise ApiError(400, "'end' must be on or after 'start'.")
    if (end - start).days > CALENDAR_MAX_DAYS:
        raise ApiError(400, f"Ask for at most {CALENDAR_MAX_DAYS} days at a time.")
    tutor_id = _calendar_tutor(ctx, ctx.q("tutor_id"), allow_all=True)
    events = db.calendar_events(ctx.conn, tutor_id, start.isoformat(), end.isoformat())
    return {"events": with_actions(ctx, events), "tutor_id": tutor_id}


@route("GET", "/api/calendar/students")
def calendar_students(ctx):
    tutor_id = _calendar_tutor(ctx, ctx.q("tutor_id"))
    date = parse_date(ctx.q("date") or db.today().isoformat())
    rows = ctx.conn.execute(
        """SELECT s.id, s.first_name || ' ' || s.last_name AS name, s.status FROM assignments a
           JOIN students s ON s.id = a.student_id
           WHERE a.tutor_id = ? AND a.start_date <= ? AND (a.end_date IS NULL OR a.end_date >= ?)
           GROUP BY s.id ORDER BY s.last_name, s.first_name""",
        (tutor_id, date.isoformat(), date.isoformat())).fetchall()
    return {"items": [dict(r) for r in rows]}


@route("GET", "/api/calendar/requests")
def calendar_requests(ctx):
    if ctx.is_staff:
        events = db.calendar_events(ctx.conn, created_by=ctx.user["id"], newest_first=True)
        events = [e for e in events if e["origin"] == "staff"]
    else:
        events = db.calendar_events(ctx.conn, tutor_id=ctx.user["id"], status="pending")
    return {"events": with_actions(ctx, events)}


@route("POST", "/api/calendar")
def calendar_create(ctx):
    tutor_id = _calendar_tutor(ctx, ctx.body.get("tutor_id"))
    v = _validate_event(ctx, ctx.body, tutor_id)
    origin = "staff" if ctx.is_staff else "tutor"
    cur = ctx.conn.execute(
        """INSERT INTO calendar_events (tutor_id, date, start_time, end_time, status, origin, notes, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (tutor_id, v["date"], v["start_time"], v["end_time"], "pending" if ctx.is_staff else "confirmed",
         origin, v["notes"], ctx.user["id"]))
    _save_students(ctx.conn, cur.lastrowid, v["student_ids"])
    ev = db.calendar_event(ctx.conn, cur.lastrowid)
    if ctx.is_staff:
        db.notify(ctx.conn, tutor_id, "calendar",
                  f"{ctx.user['name']} proposed a session: {event_label(ev)}. Please approve or reject it.",
                  link=event_link(ev))
        db.audit(ctx.conn, ctx.user["id"], "calendar.propose", f"{ev['tutor_name']}: {event_label(ev)}")
    return {"event": with_actions(ctx, [ev])[0]}


@route("PUT", r"/api/calendar/(?P<id>\d+)")
def calendar_update(ctx):
    ev = check_event_access(ctx)
    if "edit" not in event_actions(ctx, ev):
        if ev["status"] in ("rejected", "cancelled"):
            raise ApiError(409, f"This session was {ev['status']} and can't be changed.")
        if ctx.is_staff:
            raise ApiError(403, "Staff can only edit pending sessions they proposed.")
        raise ApiError(409, "Approve or reject this proposed session instead of editing it.")
    v = _validate_event(ctx, ctx.body, ev["tutor_id"], ev["id"])
    ctx.conn.execute(
        "UPDATE calendar_events SET date = ?, start_time = ?, end_time = ?, notes = ?, updated_at = ? WHERE id = ?",
        (v["date"], v["start_time"], v["end_time"], v["notes"], db.now_iso(), ev["id"]))
    _save_students(ctx.conn, ev["id"], v["student_ids"])
    ev = db.calendar_event(ctx.conn, ev["id"])
    if ctx.is_staff:
        db.notify(ctx.conn, ev["tutor_id"], "calendar",
                  f"{ctx.user['name']} changed a proposed session: {event_label(ev)}. Please approve or reject it.",
                  link=event_link(ev))
        db.audit(ctx.conn, ctx.user["id"], "calendar.edit", f"{ev['tutor_name']}: {event_label(ev)}")
    return {"event": with_actions(ctx, [ev])[0]}


def _pending_for_tutor(ctx, verb):
    ev = check_event_access(ctx)
    if ev["status"] != "pending":
        raise ApiError(409, f"Only pending sessions can be {verb}. This one is {ev['status']}.")
    return ev


@route("POST", r"/api/calendar/(?P<id>\d+)/approve", role="tutor")
def calendar_approve(ctx):
    ev = _pending_for_tutor(ctx, "approved")
    clash = db.confirmed_overlap(ctx.conn, ev["tutor_id"], ev["date"], ev["start_time"], ev["end_time"], ev["id"])
    if clash:
        raise ApiError(409, f"This overlaps a confirmed session ({event_label(clash)}). Cancel or move that one first.",
                       conflict_id=clash["id"])
    ctx.conn.execute(
        "UPDATE calendar_events SET status = 'confirmed', responded_by = ?, responded_at = ?, updated_at = ? WHERE id = ?",
        (ctx.user["id"], db.now_iso(), db.now_iso(), ev["id"]))
    db.notify(ctx.conn, ev["created_by"], "calendar", f"{ctx.user['name']} approved {event_label(ev)}.",
              link=event_link(ev, staff=True))
    return {"event": with_actions(ctx, [db.calendar_event(ctx.conn, ev["id"])])[0]}


@route("POST", r"/api/calendar/(?P<id>\d+)/reject", role="tutor")
def calendar_reject(ctx):
    ev = _pending_for_tutor(ctx, "rejected")
    note = (ctx.body.get("note") or "")[:500]
    ctx.conn.execute(
        """UPDATE calendar_events SET status = 'rejected', responded_by = ?, responded_at = ?, response_note = ?,
           updated_at = ? WHERE id = ?""", (ctx.user["id"], db.now_iso(), note, db.now_iso(), ev["id"]))
    db.notify(ctx.conn, ev["created_by"], "calendar",
              f"{ctx.user['name']} rejected {event_label(ev)}" + (f": “{note[:200]}”" if note else "."),
              link=event_link(ev, staff=True))
    return {"event": with_actions(ctx, [db.calendar_event(ctx.conn, ev["id"])])[0]}


@route("POST", r"/api/calendar/(?P<id>\d+)/cancel")
def calendar_cancel(ctx):
    ev = check_event_access(ctx)
    if ev["status"] in ("rejected", "cancelled"):
        raise ApiError(409, f"This session is already {ev['status']}.")
    if "cancel" not in event_actions(ctx, ev):
        raise ApiError(409, "Approve or reject this proposed session instead of cancelling it.")
    reason = (ctx.body.get("reason") or "")[:500]
    ctx.conn.execute(
        """UPDATE calendar_events SET status = 'cancelled', cancelled_by = ?, cancelled_at = ?, cancel_reason = ?,
           updated_at = ? WHERE id = ?""", (ctx.user["id"], db.now_iso(), reason, db.now_iso(), ev["id"]))
    suffix = f": “{reason[:200]}”" if reason else "."
    if ctx.is_staff:
        withdrawn = ev["status"] == "pending" and ev["created_by"] == ctx.user["id"]
        verb = "withdrew the proposed session" if withdrawn else "cancelled"
        db.notify(ctx.conn, ev["tutor_id"], "calendar", f"{ctx.user['name']} {verb} {event_label(ev)}{suffix}",
                  link=event_link(ev))
        db.audit(ctx.conn, ctx.user["id"], "calendar.withdraw" if withdrawn else "calendar.cancel",
                 f"{ev['tutor_name']}: {event_label(ev)}" + (f" ({reason[:200]})" if reason else ""))
    elif ev["origin"] == "staff":
        db.notify(ctx.conn, ev["created_by"], "calendar", f"{ctx.user['name']} cancelled {event_label(ev)}{suffix}",
                  link=event_link(ev, staff=True))
    return {"event": with_actions(ctx, [db.calendar_event(ctx.conn, ev["id"])])[0]}


# ---------- staff: monthly overview ----------

@route("GET", "/api/staff/overview", role="staff")
def staff_overview(ctx):
    month = ctx.month()
    rows, counts = [], {"not_started": 0, "in_progress": 0, "returned": 0, "submitted": 0, "reviewed": 0}
    total_hours = 0.0
    for a in db.active_assignments(ctx.conn, month):
        b = db.report_bundle(ctx.conn, a["tutor_id"], a["student_id"], month)
        r = b["report"]
        counts[r["status"]] += 1
        if r["status"] in ("submitted", "reviewed"):
            total_hours += b["totals"]["total"]
        rows.append({"tutor_id": a["tutor_id"], "tutor_name": a["tutor_name"], "tutor_email": a["tutor_email"],
                     "student_id": a["student_id"], "student_name": a["student_name"],
                     "student_status": a["student_status"], "schedule": a["schedule"],
                     "meeting_place": a["meeting_place"], "status": r["status"], "totals": b["totals"],
                     "submitted_at": r["submitted_at"], "leaving": bool(r["leaving_date"] or r["leaving_reason"]),
                     "achievements": len(r["achievements"]), "fy_total": b["fiscal"]["totals"]["total"]})
    first, last = db.month_bounds(month)
    return {"month": month, "month_label": first.strftime("%B %Y"), "rows": rows, "counts": counts,
            "submitted_hours": round(total_hours, 2), "month_closed": last < db.today(),
            "fiscal_year": db.fiscal_year_label(month)}


# ---------- staff: students ----------

@route("GET", "/api/staff/students", role="staff")
def staff_students(ctx):
    month = db.today().strftime("%Y-%m")
    fy_start = db.fiscal_year_start(month).isoformat()
    rows = ctx.conn.execute(
        """SELECT s.*,
             (SELECT GROUP_CONCAT(u.name, ', ') FROM assignments a JOIN users u ON u.id = a.tutor_id
               WHERE a.student_id = s.id AND a.end_date IS NULL) AS tutors,
             (SELECT COUNT(*) FROM assignments a WHERE a.student_id = s.id AND a.end_date IS NULL) AS open_assignments,
             (SELECT COALESCE(SUM(tutoring_hours + homework_hours), 0) FROM sessions x
               WHERE x.student_id = s.id AND x.date >= ?) AS fy_hours,
             (SELECT MAX(date) FROM sessions x WHERE x.student_id = s.id) AS last_session
           FROM students s ORDER BY s.status = 'dropped', s.last_name, s.first_name""", (fy_start,)).fetchall()
    return {"items": [dict(r) for r in rows], "fiscal_year": db.fiscal_year_label(month)}


@route("GET", r"/api/staff/students/(?P<id>\d+)", role="staff")
def staff_student_detail(ctx):
    sid = int(ctx.params["id"])
    s = ctx.conn.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not s:
        raise ApiError(404, "Student not found.")
    assignments = ctx.conn.execute(
        """SELECT a.*, u.name AS tutor_name FROM assignments a JOIN users u ON u.id = a.tutor_id
           WHERE a.student_id = ? ORDER BY a.end_date IS NOT NULL, a.start_date DESC""", (sid,)).fetchall()
    this_month = db.today().strftime("%Y-%m")
    history = []
    for m in reversed([m for m in db.fiscal_months(this_month) if m <= this_month]):
        first, last = db.month_bounds(m)
        for a in assignments:
            if a["start_date"] <= last.isoformat() and (a["end_date"] is None or a["end_date"] >= first.isoformat()):
                b = db.report_bundle(ctx.conn, a["tutor_id"], sid, m)
                history.append({"month": m, "month_label": b["month_label"], "tutor_id": a["tutor_id"],
                                "tutor_name": a["tutor_name"], "status": b["report"]["status"], "totals": b["totals"]})
    return {"student": dict(s), "assignments": [dict(a) for a in assignments], "history": history,
            "fiscal_year": db.fiscal_year_label(this_month)}


@route("POST", "/api/staff/students", role="staff")
def staff_student_create(ctx):
    b = ctx.body
    need(b, "first_name", "last_name")
    enrolled = b.get("enrolled_on") or db.today().isoformat()
    parse_date(enrolled, "enrolled_on")
    cur = ctx.conn.execute(
        "INSERT INTO students (first_name, last_name, program, enrolled_on, notes) VALUES (?, ?, ?, ?, ?)",
        (b["first_name"].strip(), b["last_name"].strip(), b.get("program") or "ESL", enrolled, b.get("notes") or ""))
    db.audit(ctx.conn, ctx.user["id"], "student.create", f"{b['first_name']} {b['last_name']}")
    return {"id": cur.lastrowid}


@route("PUT", r"/api/staff/students/(?P<id>\d+)", role="staff")
def staff_student_update(ctx):
    b, sid = ctx.body, int(ctx.params["id"])
    need(b, "first_name", "last_name")
    ctx.conn.execute("UPDATE students SET first_name = ?, last_name = ?, program = ?, notes = ? WHERE id = ?",
                     (b["first_name"].strip(), b["last_name"].strip(), b.get("program") or "ESL",
                      b.get("notes") or "", sid))
    db.audit(ctx.conn, ctx.user["id"], "student.edit", f"#{sid} {b['first_name']} {b['last_name']}")
    return {"ok": True}


@route("POST", r"/api/staff/students/(?P<id>\d+)/status", role="staff")
def staff_student_status(ctx):
    sid, b = int(ctx.params["id"]), ctx.body
    s = ctx.conn.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not s:
        raise ApiError(404, "Student not found.")
    new = b.get("status")
    name = f"{s['first_name']} {s['last_name']}"
    if new == "dropped":
        need(b, "date", "reason")
        date = parse_date(b["date"]).isoformat()
        ctx.conn.execute("UPDATE students SET status = 'dropped', left_on = ?, leave_reason = ? WHERE id = ?",
                         (date, b["reason"][:500], sid))
        ended = ctx.conn.execute(
            "UPDATE assignments SET end_date = ? WHERE student_id = ? AND end_date IS NULL", (date, sid)).rowcount
        db.audit(ctx.conn, ctx.user["id"], "student.drop", f"{name} dropped {date}: {b['reason'][:200]} ({ended} assignment(s) ended)")
    elif new == "paused":
        if s["status"] == "dropped":
            raise ApiError(409, "Dropped students must be readmitted first.")
        ctx.conn.execute("UPDATE students SET status = 'paused' WHERE id = ?", (sid,))
        db.audit(ctx.conn, ctx.user["id"], "student.pause", name)
    elif new == "active":
        if s["status"] == "dropped":
            if not b.get("readmit"):
                raise ApiError(409, "A drop is permanent. Readmitting is an admin decision — confirm to readmit.")
            ctx.conn.execute("UPDATE students SET status = 'active', left_on = NULL, leave_reason = NULL WHERE id = ?", (sid,))
            db.audit(ctx.conn, ctx.user["id"], "student.readmit", f"{name} readmitted (previously left {s['left_on']}: {s['leave_reason']})")
        else:
            ctx.conn.execute("UPDATE students SET status = 'active' WHERE id = ?", (sid,))
            db.audit(ctx.conn, ctx.user["id"], "student.resume", name)
    else:
        raise ApiError(400, "Status must be active, paused or dropped.")
    return {"ok": True}


# ---------- staff: tutors & accounts ----------

@route("GET", "/api/staff/tutors", role="staff")
def staff_tutors(ctx):
    rows = ctx.conn.execute(
        """SELECT u.*,
             (SELECT COUNT(*) FROM assignments a WHERE a.tutor_id = u.id AND a.end_date IS NULL) AS students,
             (SELECT MAX(date) FROM sessions x WHERE x.tutor_id = u.id) AS last_session
           FROM users u ORDER BY u.role DESC, u.active DESC, u.name""").fetchall()
    return {"items": [{**user_public(r), "students": r["students"], "last_session": r["last_session"],
                       "created_at": r["created_at"]} for r in rows]}


def _temp_password():
    return "-".join(secrets.token_hex(2) for _ in range(3))


@route("POST", "/api/staff/tutors", role="staff")
def staff_tutor_create(ctx):
    b = ctx.body
    need(b, "name", "email")
    role = b.get("role") or "tutor"
    if role not in ("tutor", "staff"):
        raise ApiError(400, "Role must be tutor or staff.")
    if "@" not in b["email"]:
        raise ApiError(400, "Enter a valid email address.")
    temp = _temp_password()
    try:
        cur = ctx.conn.execute(
            """INSERT INTO users (name, email, phone, role, password_hash, must_change_password, training_hours)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (b["name"].strip(), b["email"].strip(), b.get("phone") or "", role, db.hash_password(temp),
             float(b.get("training_hours") or 0)))
    except sqlite3.IntegrityError:
        raise ApiError(409, "An account with that email already exists.")
    db.notify(ctx.conn, cur.lastrowid, "welcome",
              "Welcome to LVAEP tutor reporting! Log each session here and submit each month when you're done.")
    db.audit(ctx.conn, ctx.user["id"], "account.create", f"{role} {b['name']} <{b['email']}>")
    return {"id": cur.lastrowid, "temp_password": temp}


@route("PUT", r"/api/staff/tutors/(?P<id>\d+)", role="staff")
def staff_tutor_update(ctx):
    uid, b = int(ctx.params["id"]), ctx.body
    need(b, "name", "email")
    active = 1 if b.get("active", True) else 0
    if uid == ctx.user["id"] and not active:
        raise ApiError(400, "You can't deactivate your own account.")
    try:
        ctx.conn.execute("UPDATE users SET name = ?, email = ?, phone = ?, training_hours = ?, active = ? WHERE id = ?",
                         (b["name"].strip(), b["email"].strip(), b.get("phone") or "",
                          float(b.get("training_hours") or 0), active, uid))
    except sqlite3.IntegrityError:
        raise ApiError(409, "An account with that email already exists.")
    if not active:
        ctx.conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (uid,))
    db.audit(ctx.conn, ctx.user["id"], "account.edit", f"#{uid} {b['name']}{'' if active else ' (deactivated)'}")
    return {"ok": True}


@route("POST", r"/api/staff/tutors/(?P<id>\d+)/reset-password", role="staff")
def staff_tutor_reset(ctx):
    uid = int(ctx.params["id"])
    temp = _temp_password()
    ctx.conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                     (db.hash_password(temp), uid))
    ctx.conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (uid,))
    db.audit(ctx.conn, ctx.user["id"], "account.reset_password", f"#{uid}")
    return {"temp_password": temp}


# ---------- staff: assignments ----------

@route("GET", "/api/staff/assignments", role="staff")
def staff_assignments(ctx):
    rows = ctx.conn.execute(
        """SELECT a.*, u.name AS tutor_name, s.first_name || ' ' || s.last_name AS student_name, s.status AS student_status
           FROM assignments a JOIN users u ON u.id = a.tutor_id JOIN students s ON s.id = a.student_id
           ORDER BY a.end_date IS NOT NULL, u.name, s.last_name""").fetchall()
    return {"items": [dict(r) for r in rows]}


@route("POST", "/api/staff/assignments", role="staff")
def staff_assignment_create(ctx):
    b = ctx.body
    need(b, "tutor_id", "student_id", "start_date")
    tutor_id, student_id = int(b["tutor_id"]), int(b["student_id"])
    start = parse_date(b["start_date"], "start_date").isoformat()
    t = ctx.conn.execute("SELECT * FROM users WHERE id = ? AND role = 'tutor'", (tutor_id,)).fetchone()
    s = ctx.conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not t or not t["active"]:
        raise ApiError(400, "Choose an active tutor.")
    if not s:
        raise ApiError(400, "Choose a student.")
    if s["status"] == "dropped":
        raise ApiError(409, "This student was dropped. Readmit them before assigning a tutor.")
    if ctx.conn.execute("SELECT 1 FROM assignments WHERE tutor_id = ? AND student_id = ? AND end_date IS NULL",
                        (tutor_id, student_id)).fetchone():
        raise ApiError(409, "This tutor is already assigned to this student.")
    warnings = []
    if t["training_hours"] < 10:
        warnings.append(f"{t['name']} has completed {t['training_hours']:g} of 10 training hours.")
    load = ctx.conn.execute("SELECT COUNT(*) AS c FROM assignments WHERE tutor_id = ? AND end_date IS NULL",
                            (tutor_id,)).fetchone()["c"]
    if load >= 5:
        warnings.append(f"{t['name']} already has {load} students (usual group is 3–5).")
    if warnings and not b.get("confirm"):
        raise ApiError(422, " ".join(warnings), needs_confirm=True)
    cur = ctx.conn.execute(
        "INSERT INTO assignments (tutor_id, student_id, meeting_place, schedule, start_date) VALUES (?, ?, ?, ?, ?)",
        (tutor_id, student_id, b.get("meeting_place") or "", b.get("schedule") or "", start))
    student_name = f"{s['first_name']} {s['last_name']}"
    db.notify(ctx.conn, tutor_id, "assigned",
              f"You've been assigned a new student: {student_name}"
              f"{' — ' + b['schedule'] if b.get('schedule') else ''}{' at ' + b['meeting_place'] if b.get('meeting_place') else ''}.",
              link=f"#/tutor/student/{student_id}")
    db.audit(ctx.conn, ctx.user["id"], "assignment.create", f"{t['name']} ↔ {student_name} from {start}")
    return {"id": cur.lastrowid}


@route("PUT", r"/api/staff/assignments/(?P<id>\d+)", role="staff")
def staff_assignment_update(ctx):
    aid, b = int(ctx.params["id"]), ctx.body
    ctx.conn.execute("UPDATE assignments SET meeting_place = ?, schedule = ? WHERE id = ?",
                     (b.get("meeting_place") or "", b.get("schedule") or "", aid))
    db.audit(ctx.conn, ctx.user["id"], "assignment.edit", f"#{aid}")
    return {"ok": True}


@route("POST", r"/api/staff/assignments/(?P<id>\d+)/end", role="staff")
def staff_assignment_end(ctx):
    aid = int(ctx.params["id"])
    a = ctx.conn.execute("SELECT * FROM assignments WHERE id = ?", (aid,)).fetchone()
    if not a:
        raise ApiError(404, "Assignment not found.")
    end = parse_date(ctx.body.get("end_date") or db.today().isoformat(), "end_date").isoformat()
    if end < a["start_date"]:
        raise ApiError(400, "End date is before the assignment started.")
    ctx.conn.execute("UPDATE assignments SET end_date = ? WHERE id = ?", (end, aid))
    t, s = names(ctx.conn, a["tutor_id"], a["student_id"])
    db.audit(ctx.conn, ctx.user["id"], "assignment.end", f"{t} ↔ {s} ended {end}")
    return {"ok": True}


# ---------- staff: reminders & activity ----------

@route("GET", "/api/staff/reminders", role="staff")
def staff_reminders(ctx):
    settings = {r["key"]: r["value"] for r in ctx.conn.execute("SELECT * FROM settings")}
    runs = ctx.conn.execute(
        """SELECT r.*, u.name AS triggered_by_name FROM reminder_runs r LEFT JOIN users u ON u.id = r.triggered_by
           ORDER BY r.id DESC LIMIT 40""").fetchall()
    return {"settings": settings, "runs": [dict(r) for r in runs], "today": db.today().isoformat()}


@route("PUT", "/api/staff/reminders/settings", role="staff")
def staff_reminder_settings(ctx):
    for key in db.DEFAULT_SETTINGS:
        if key in ctx.body:
            ctx.conn.execute("UPDATE settings SET value = ? WHERE key = ?", (str(ctx.body[key]), key))
    db.audit(ctx.conn, ctx.user["id"], "reminders.settings", json.dumps(ctx.body))
    return {"ok": True}


@route("POST", "/api/staff/reminders/send", role="staff")
def staff_reminder_send(ctx):
    month = ctx.body.get("month") or db.today().strftime("%Y-%m")
    if not db.valid_month(month):
        raise ApiError(400, "Invalid month.")
    n = reminders.send_month_reminders(ctx.conn, month, "manual", triggered_by=ctx.user["id"])
    db.audit(ctx.conn, ctx.user["id"], "reminders.send", f"{month}: {n} tutor(s)")
    return {"recipients": n}


@route("POST", "/api/staff/reminders/run", role="staff")
def staff_reminder_run(ctx):
    ctx.conn.commit()
    sent = reminders.run_scheduled(ctx.conn)
    return {"sent": [{"kind": k, "recipients": n} for k, n in sent]}


@route("GET", "/api/staff/activity", role="staff")
def staff_activity(ctx):
    rows = ctx.conn.execute(
        """SELECT l.*, u.name AS user_name FROM audit_log l LEFT JOIN users u ON u.id = l.user_id
           ORDER BY l.id DESC LIMIT 200""").fetchall()
    return {"items": [dict(r) for r in rows]}


# ---------- exports ----------

@route("GET", "/export/sessions.csv", role="staff")
def export_sessions(ctx):
    month = ctx.month()
    return Raw(exports.sessions_csv(ctx.conn, month), "text/csv; charset=utf-8", f"lvaep-sessions-{month}.csv")


@route("GET", "/export/summary.csv", role="staff")
def export_summary(ctx):
    month = ctx.month()
    return Raw(exports.summary_csv(ctx.conn, month), "text/csv; charset=utf-8", f"lvaep-monthly-summary-{month}.csv")


@route("GET", "/print")
def print_forms(ctx):
    month = ctx.month()
    label = db.month_bounds(month)[0].strftime("%B %Y")
    if ctx.q("tutor") and ctx.q("student"):
        tutor_id, student_id = int(ctx.q("tutor")), int(ctx.q("student"))
        check_pair_access(ctx, tutor_id, student_id)
        if ctx.q("fragment") == "1":  # just the form, for the app's built-in print (button / Cmd+P)
            return Raw(exports.attendance_form(ctx.conn, tutor_id, student_id, month), "text/html; charset=utf-8")
        t, s = names(ctx.conn, tutor_id, student_id)
        html = exports.printable(ctx.conn, [(tutor_id, student_id)], month, f"{s} — {label}")
    elif ctx.is_staff:
        wanted = (ctx.q("status") or "submitted,reviewed").split(",")
        pairs = []
        for a in db.active_assignments(ctx.conn, month):
            status = db.report_bundle(ctx.conn, a["tutor_id"], a["student_id"], month)["report"]["status"]
            if status in wanted:
                pairs.append((a["tutor_id"], a["student_id"]))
        html = exports.printable(ctx.conn, pairs, month, f"LVAEP monthly forms — {label}")
    else:
        raise ApiError(403, "Only staff can print every report.")
    return Raw(html, "text/html; charset=utf-8")


# ---------- HTTP plumbing ----------

class Handler(BaseHTTPRequestHandler):
    server_version = "LVAEP/0.1"

    def log_message(self, fmt, *args):
        if os.environ.get("LVAEP_QUIET") != "1":
            super().log_message(fmt, *args)

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, path.lstrip("/")))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            full = os.path.join(STATIC_DIR, "index.html")
        types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
                 ".png": "image/png", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json"}
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            self.send(200, f.read(), types.get(ext, "application/octet-stream") + "; charset=utf-8")

    def dispatch(self, method):
        url = urlparse(self.path)
        path = url.path
        if method == "GET" and not (path.startswith("/api/") or path.startswith("/export/") or path == "/print"):
            return self.serve_static(path)
        for m, pattern, fn, role, auth in ROUTES:
            match = pattern.match(path)
            if m == method and match:
                return self.run(fn, role, auth, match.groupdict(), parse_qs(url.query))
        self.send(404, json.dumps({"error": "Not found."}))

    def run(self, fn, role, auth, params, query):
        conn = db.connect()
        try:
            body = {}
            if self.command in ("POST", "PUT"):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    if "application/json" not in (self.headers.get("Content-Type") or ""):
                        raise ApiError(415, "Send JSON.")
                    body = json.loads(self.rfile.read(length) or b"{}")
            jar = cookies.SimpleCookie(self.headers.get("Cookie") or "")
            token = jar[COOKIE].value if COOKIE in jar else None
            user = None
            if token:
                user = conn.execute(
                    """SELECT u.* FROM auth_tokens t JOIN users u ON u.id = t.user_id
                       WHERE t.token = ? AND t.expires_at > ? AND u.active = 1""",
                    (token, dt.datetime.now().isoformat())).fetchone()
            if auth and not user:
                raise ApiError(401, "Please sign in.")
            if role and user["role"] != role:
                raise ApiError(403, "You don't have access to this page.")
            ctx = Ctx(conn, user, params, query, body)
            ctx.token, ctx.set_cookie = token, None
            result = fn(ctx)
            conn.commit()
            headers = {}
            if ctx.set_cookie is not None:
                age = TOKEN_DAYS * 86400 if ctx.set_cookie else 0
                headers["Set-Cookie"] = f"{COOKIE}={ctx.set_cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}"
            if isinstance(result, Raw):
                if result.filename:
                    headers["Content-Disposition"] = f'attachment; filename="{result.filename}"'
                self.send(200, result.body, result.content_type, headers)
            else:
                self.send(200, json.dumps(result), headers=headers)
        except ApiError as e:
            conn.rollback()
            if self.path.startswith("/print") or self.path.startswith("/export"):
                self.send(e.status, f"<p style='font-family:sans-serif'>{e.message} <a href='/'>Back to the app</a></p>",
                          "text/html; charset=utf-8")
            else:
                self.send(e.status, json.dumps({"error": e.message, **e.extra}))
        except json.JSONDecodeError:
            conn.rollback()
            self.send(400, json.dumps({"error": "Request body is not valid JSON."}))
        except Exception:
            conn.rollback()
            traceback.print_exc()
            self.send(500, json.dumps({"error": "Something went wrong on the server."}))
        finally:
            conn.close()


def scheduler_loop(interval):
    while True:
        try:
            conn = db.connect()
            sent = reminders.run_scheduled(conn)
            conn.close()
            for kind, n in sent:
                print(f"[reminders] {kind}: notified {n} tutor(s)")
        except Exception:
            traceback.print_exc()
        time.sleep(interval)


def serve(host="127.0.0.1", port=8070, scheduler=True):
    conn = db.connect()
    db.init(conn)
    conn.close()
    httpd = ThreadingHTTPServer((host, port), Handler)
    if scheduler:
        threading.Thread(target=scheduler_loop, args=(1800,), daemon=True).start()
    return httpd
