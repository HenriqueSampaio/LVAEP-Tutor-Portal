"""Staff exports: month CSVs and LVAEP's Student Monthly Attendance & Achievement Form (print → PDF)."""
import calendar
import csv
import io
import json
from html import escape

from . import db


def _hours(x):
    return f"{x:g}" if x else "0"


def sessions_csv(conn, month):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Month", "Tutor", "Student", "Meeting place", "Days/times", "Date", "Attendance",
                "Tutoring hours", "Homework hours", "Total hours", "Note", "Report status"])
    for a in db.active_assignments(conn, month):
        b = db.report_bundle(conn, a["tutor_id"], a["student_id"], month)
        for s in b["sessions"]:
            w.writerow([month, b["tutor"]["name"], b["student"]["name"], a["meeting_place"], a["schedule"],
                        s["date"], db.ATTENDANCE_CODES.get(s["attendance"], s["attendance"]),
                        s["tutoring_hours"], s["homework_hours"],
                        round(s["tutoring_hours"] + s["homework_hours"], 2), s["note"], b["report"]["status"]])
    return out.getvalue()


def summary_csv(conn, month):
    out = io.StringIO()
    w = csv.writer(out)
    fy = db.fiscal_year_label(month)
    w.writerow(["Month", "Tutor", "Student", "Program", "Meeting place", "Days/times", "Report status",
                "Submitted at", "Sessions attended", "Tutoring hours", "Homework hours", "Total hours",
                f"{fy} tutoring to date", f"{fy} homework to date", f"{fy} total to date",
                "Achievements", "Achievement notes", "Leaving date", "Leaving reason"])
    for a in db.active_assignments(conn, month):
        b = db.report_bundle(conn, a["tutor_id"], a["student_id"], month)
        r, t, f = b["report"], b["totals"], b["fiscal"]["totals"]
        w.writerow([month, b["tutor"]["name"], b["student"]["name"], b["student"]["program"],
                    a["meeting_place"], a["schedule"], r["status"], r["submitted_at"] or "",
                    t["attended"], t["tutoring"], t["homework"], t["total"],
                    f["tutoring"], f["homework"], f["total"],
                    "; ".join(r["achievements"] + ([f"Other: {r['achievement_other']}"] if r["achievement_other"] else [])),
                    r["achievement_notes"],
                    r["leaving_date"] or "", r["leaving_reason"]])
    return out.getvalue()


# ---------- the official form ----------

ATTENDANCE_MARKS = {"student_absent": "SA", "tutor_absent": "TA", "holiday": "H"}  # "cancelled" has no code on the form
STATUS_LABELS = {"not_started": "Not started", "in_progress": "Draft", "returned": "Returned to tutor",
                 "submitted": "Submitted", "reviewed": "Reviewed"}


def _split_schedule(schedule):
    """'Tuesdays, 6:00–8:00 pm' -> ('Tuesdays', '6:00–8:00 pm')."""
    days, _, times = (schedule or "").partition(",")
    return days.strip(), times.strip()


def form_data(conn, tutor_id, student_id, month):
    """Everything on one tutor–student form: the fiscal year's day-by-month hours through `month`,
    goals attained so far, and whether the student stopped."""
    b = db.report_bundle(conn, tutor_id, student_id, month)
    months = db.fiscal_months(month)
    fy_start, (_, last_day) = db.fiscal_year_start(month), db.month_bounds(month)
    cells, totals = {}, {m: 0.0 for m in months if m <= month}
    for s in conn.execute(
        """SELECT date, attendance, tutoring_hours, homework_hours FROM sessions
           WHERE tutor_id = ? AND student_id = ? AND date BETWEEN ? AND ?""",
        (tutor_id, student_id, fy_start.isoformat(), last_day.isoformat()),
    ):
        m, day = s["date"][:7], int(s["date"][8:])
        if s["attendance"] == "present":
            hours = round(s["tutoring_hours"] + s["homework_hours"], 2)
            cells[(m, day)] = _hours(hours)
            totals[m] += hours
        else:
            cells[(m, day)] = ATTENDANCE_MARKS.get(s["attendance"], "")
    reports = conn.execute(
        "SELECT * FROM reports WHERE tutor_id = ? AND student_id = ? AND month BETWEEN ? AND ? ORDER BY month",
        (tutor_id, student_id, months[0], month),
    ).fetchall()
    attained, others, stopped, reason = set(), [], False, ""
    for r in reports:
        ticked = json.loads(r["achievements"])
        attained.update(ticked)
        for x in [r["achievement_other"]] + [t for t in ticked if t not in db.ACHIEVEMENTS]:
            if x and x not in others:
                others.append(x)
        if r["leaving_date"] or r["leaving_reason"]:
            stopped = True
            reason = r["leaving_reason"] + (f" (last session {r['leaving_date']})" if r["leaving_date"] else "")
    student = conn.execute("SELECT status, left_on, leave_reason FROM students WHERE id = ?", (student_id,)).fetchone()
    if student["status"] == "dropped" and student["left_on"] and fy_start.isoformat() <= student["left_on"] <= last_day.isoformat():
        stopped = True
        reason = reason or f"{student['leave_reason'] or 'Dropped'} (left {student['left_on']})"
    days, times = _split_schedule(b["assignment"]["schedule"] if b["assignment"] else "")
    return {"bundle": b, "months": months, "cells": cells, "totals": totals, "attained": attained,
            "others": others, "stopped": stopped, "reason": reason.strip(),
            "site": b["assignment"]["meeting_place"] if b["assignment"] else "", "days": days, "times": times}


def attendance_form(conn, tutor_id, student_id, month):
    """One printable form as an HTML <section> (styled by static/print-form.css)."""
    d = form_data(conn, tutor_id, student_id, month)
    b = d["bundle"]
    head = "".join(f"<th>{db.month_bounds(m)[0]:%b}</th>" for m in d["months"])
    rows = []
    for day in range(1, 32):
        tds = []
        for m in d["months"]:
            year, mon = (int(x) for x in m.split("-"))
            if day > calendar.monthrange(year, mon)[1]:
                tds.append(f"<td class=na data-month={m} data-day={day}></td>")
            else:
                tds.append(f"<td data-month={m} data-day={day}>{escape(d['cells'].get((m, day), ''))}</td>")
        rows.append(f"<tr><th>{day}</th>{''.join(tds)}</tr>")
    totals = "".join(f"<td data-month={m} data-day=total>{_hours(d['totals'][m]) if m in d['totals'] else ''}</td>"
                     for m in d["months"])

    def box(on):
        return f"<span class=box>{'&#10003;' if on else ''}</span>"

    groups = "".join(
        f"<div class=goal-group><b>{escape(heading)}</b><ol>"
        + "".join(f"<li><span>{escape(item)}</span>{box(item in d['attained'])}</li>" for item in items)
        + "</ol></div>"
        for heading, items in db.ACHIEVEMENT_GROUPS
    )
    others = escape("; ".join(d["others"]))
    status = STATUS_LABELS.get(b["report"]["status"], b["report"]["status"])
    return f"""<section class="lv-form" data-tutor="{b['tutor']['id']}" data-student="{b['student']['id']}">
  <div class=frame>
    <div class=title>
      <div class=org>LITERACY VOLUNTEERS OF AMERICA, ESSEX/PASSAIC COUNTY</div>
      <div class=org>Student Monthly Attendance &amp; Achievement Form – {escape(b['fiscal_year'])}</div>
      <div class=names><span>Tutor:</span><u>{escape(b['tutor']['name'])}</u><span>Student:</span><u>{escape(b['student']['name'])}</u></div>
    </div>
    <div class=contact><b>Contact Information</b><i>90 Broad Street, Bloomfield, NJ 07003</i><i>Bloomfield Public Library</i>
      <i>info@lvaep.org -- (973) 566-6200 x216</i></div>
    <div class=att-head><b><u>ATTENDANCE</u></b>
      <i>Please <u>complete a separate form for each student you tutor</u>.</i>
      <i>Place number of hours tutored in the appropriate box (day and month).</i>
      <small>(For Internal Use Only: <b>TA</b>: Tutor Absent <b>SA</b>: Student Absent <b>H</b>: Holiday)</small></div>
    <div class=ach-head><b><u>ACHIEVEMENTS</u></b><i>Place a "&#8730;" next to each student's goal when attained.</i></div>
    <table class=grid><thead><tr><th></th>{head}</tr></thead><tbody>{''.join(rows)}</tbody>
      <tfoot><tr><th>Total</th>{totals}</tr></tfoot></table>
    <div class=goals>{groups}
      <div class=goal-group><b>E. Other(s)</b>: <span class=fill>{others}</span></div>
      <div class=stopped><b>STOPPED</b>
        <p>{box(d['stopped'])} Please place a "&#8730;" in the box if your student is no longer being tutored and notify the office ASAP.</p>
        <p><b>Reason:</b> <span class=fill>{escape(d['reason'])}</span></p></div>
    </div>
    <div class=site><span><b>Tutoring Site:</b> {escape(d['site'])}</span><span><b>Day(s):</b> {escape(d['days'])}</span>
      <span><b>Time(s):</b> {escape(d['times'])}</span></div>
  </div>
  <p class=note>Please consider adding extra time to all meetings, coordinating an extra session whenever possible, and regularly
    assigning homework (give your students credit for all completed work.)</p>
  <p class=stamp>Printed {db.today():%b} {db.today().day}, {db.today().year} · {escape(b['month_label'])} report: {escape(status)}
    · hours = tutoring + homework</p>
</section>"""


PAGE_CSS = """
body{margin:0;background:#e9ecef;font-family:system-ui,sans-serif}
.toolbar{position:sticky;top:0;z-index:1;background:#1f3a5f;color:#fff;padding:10px 16px;display:flex;gap:12px;align-items:center}
.toolbar button{font:inherit;padding:6px 14px;border-radius:6px;border:0;background:#fff;color:#1f3a5f;font-weight:600;cursor:pointer}
.empty{background:#fff;max-width:600px;margin:40px auto;padding:24px;border-radius:8px}
@media print{body{background:#fff}.toolbar{display:none}}
"""


def printable(conn, pairs, month, title):
    """A standalone page of forms with a print toolbar (what /print serves)."""
    forms = [attendance_form(conn, tutor_id, student_id, month) for tutor_id, student_id in pairs]
    body = "".join(forms) or "<p class=empty>No reports match.</p>"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><link rel=stylesheet href="/print-form.css"><style>{PAGE_CSS}</style></head><body class=print-page>
<div class=toolbar><b>{escape(title)}</b><span style="flex:1"></span>
<span>{len(forms)} form(s)</span><button onclick="window.print()">Print / Save as PDF</button></div>
{body}</body></html>"""
