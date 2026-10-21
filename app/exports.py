"""Staff exports: month CSVs and the printable individual monthly form (print → PDF)."""
import csv
import io
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
                    "; ".join(r["achievements"]), r["achievement_notes"],
                    r["leaving_date"] or "", r["leaving_reason"]])
    return out.getvalue()


PRINT_CSS = """
*{box-sizing:border-box}
body{font:13px/1.4 Georgia,'Times New Roman',serif;color:#111;margin:0;background:#e9ecef}
.toolbar{position:sticky;top:0;background:#1f3a5f;color:#fff;padding:10px 16px;display:flex;gap:12px;align-items:center;font-family:system-ui,sans-serif}
.toolbar button{font:inherit;padding:6px 14px;border-radius:6px;border:0;background:#fff;color:#1f3a5f;font-weight:600;cursor:pointer}
.page{background:#fff;width:8.5in;min-height:11in;margin:20px auto;padding:.6in .65in;box-shadow:0 2px 10px rgba(0,0,0,.15)}
h1{font-size:17px;text-align:center;margin:0;letter-spacing:.02em;text-transform:uppercase}
h2{font-size:13px;margin:18px 0 6px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1.5px solid #111;padding-bottom:2px}
.org{text-align:center;font-size:12px;margin-bottom:2px}
.sub{text-align:center;font-size:12px;margin:2px 0 14px}
table{width:100%;border-collapse:collapse}
td,th{border:1px solid #444;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#eef0f3;font-weight:bold;font-size:12px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.fields td{width:25%}
.fields td.l{background:#f6f7f9;font-weight:bold;width:18%}
tr.tot td{font-weight:bold;background:#f6f7f9}
tr.future td{color:#999}
.cb{display:inline-block;width:11px;height:11px;border:1px solid #111;margin-right:6px;vertical-align:-1px;text-align:center;line-height:10px;font-size:10px}
.ach{columns:2;column-gap:24px;margin:0;padding:0;list-style:none}
.ach li{margin:2px 0;break-inside:avoid}
.sig{display:flex;gap:24px;margin-top:22px}
.sig div{flex:1;border-top:1px solid #111;padding-top:3px;font-size:11px}
.muted{color:#555;font-size:11px}
.stamp{font-family:system-ui,sans-serif;font-size:10px;color:#555;margin-top:16px;text-align:right}
@media print{body{background:#fff}.toolbar{display:none}.page{box-shadow:none;margin:0;width:auto;min-height:0;padding:0;page-break-after:always}.page:last-child{page-break-after:auto}@page{size:letter;margin:.5in}}
"""


def _form_page(b, a):
    r = b["report"]
    att = db.ATTENDANCE_CODES
    sess_rows = "".join(
        f"<tr><td>{escape(s['date'])}</td><td>{escape(att.get(s['attendance'], s['attendance']))}</td>"
        f"<td class=n>{_hours(s['tutoring_hours'])}</td><td class=n>{_hours(s['homework_hours'])}</td>"
        f"<td class=n>{_hours(round(s['tutoring_hours'] + s['homework_hours'], 2))}</td>"
        f"<td>{escape(s['note'])}</td></tr>"
        for s in b["sessions"]
    ) or "<tr><td colspan=6 class=muted>No sessions recorded this month.</td></tr>"
    t = b["totals"]
    fy_rows = "".join(
        f"<tr class='{'future' if m['future'] else ''}'><td>{escape(_month_name(m['month']))}</td>"
        f"<td class=n>{'' if m['future'] else m['attended']}</td>"
        f"<td class=n>{'' if m['future'] else _hours(m['tutoring'])}</td>"
        f"<td class=n>{'' if m['future'] else _hours(m['homework'])}</td>"
        f"<td class=n>{'' if m['future'] else _hours(m['total'])}</td></tr>"
        for m in b["fiscal"]["months"]
    )
    ft = b["fiscal"]["totals"]
    ach = "".join(
        f"<li><span class=cb>{'✓' if item in r['achievements'] else ''}</span>{escape(item)}</li>"
        for item in db.ACHIEVEMENTS
    )
    extra = [x for x in r["achievements"] if x not in db.ACHIEVEMENTS]
    ach += "".join(f"<li><span class=cb>✓</span>{escape(x)}</li>" for x in extra)
    status_line = {
        "submitted": f"Submitted by tutor {escape(r['submitted_at'] or '')}",
        "reviewed": f"Submitted {escape(r['submitted_at'] or '')} · Reviewed by {escape(r['reviewed_by'] or 'staff')} {escape(r['reviewed_at'] or '')}",
    }.get(r["status"], "NOT YET SUBMITTED — draft copy")
    co = f" (also tutored by {escape(', '.join(b['co_tutors']))})" if b["co_tutors"] else ""
    return f"""
<section class=page>
  <div class=org>Literacy Volunteers of America — Essex &amp; Passaic Counties</div>
  <h1>Student Monthly Attendance &amp; Achievement Form</h1>
  <div class=sub>{escape(b['fiscal_year'])} · Month: <b>{escape(b['month_label'])}</b></div>
  <table class=fields>
    <tr><td class=l>Student</td><td>{escape(b['student']['name'])}{co}</td><td class=l>Tutor</td><td>{escape(b['tutor']['name'])}</td></tr>
    <tr><td class=l>Program</td><td>{escape(b['student']['program'])}</td><td class=l>Tutor phone / email</td><td>{escape(b['tutor'].get('phone') or '')}<br>{escape(b['tutor']['email'])}</td></tr>
    <tr><td class=l>Meeting place</td><td>{escape(a['meeting_place'] if a else '')}</td><td class=l>Days / times</td><td>{escape(a['schedule'] if a else '')}</td></tr>
  </table>

  <h2>Attendance &amp; hours — {escape(b['month_label'])}</h2>
  <table>
    <tr><th style="width:15%">Date</th><th style="width:20%">Attendance</th><th class=n style="width:12%">Tutoring hrs</th><th class=n style="width:12%">Homework hrs</th><th class=n style="width:10%">Total</th><th>Notes</th></tr>
    {sess_rows}
    <tr class=tot><td colspan=2>Month total ({t['attended']} sessions attended)</td><td class=n>{_hours(t['tutoring'])}</td><td class=n>{_hours(t['homework'])}</td><td class=n>{_hours(t['total'])}</td><td></td></tr>
  </table>

  <h2>Fiscal year hours to date — {escape(b['fiscal_year'])}</h2>
  <table>
    <tr><th>Month</th><th class=n>Sessions</th><th class=n>Tutoring</th><th class=n>Homework</th><th class=n>Total</th></tr>
    {fy_rows}
    <tr class=tot><td>Year to date</td><td class=n>{ft['attended']}</td><td class=n>{_hours(ft['tutoring'])}</td><td class=n>{_hours(ft['homework'])}</td><td class=n>{_hours(ft['total'])}</td></tr>
  </table>

  <h2>Achievements this month</h2>
  <ul class=ach>{ach}</ul>
  <p><b>Notes:</b> {escape(r['achievement_notes']) or '<span class=muted>—</span>'}</p>

  <h2>If the student stopped attending</h2>
  <table class=fields><tr><td class=l>Date left</td><td>{escape(r['leaving_date'] or '')}</td><td class=l>Reason</td><td>{escape(r['leaving_reason'])}</td></tr></table>

  <div class=sig><div>Tutor: {escape(b['tutor']['name'])}</div><div>LVAEP staff review</div></div>
  <div class=stamp>{status_line}</div>
</section>"""


def _month_name(month):
    return db.month_bounds(month)[0].strftime("%B %Y")


def printable(conn, pairs, month, title):
    pages = []
    for tutor_id, student_id in pairs:
        b = db.report_bundle(conn, tutor_id, student_id, month)
        pages.append(_form_page(b, b["assignment"]))
    body = "".join(pages) or "<section class=page><p>No reports match.</p></section>"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{PRINT_CSS}</style></head><body>
<div class=toolbar><b>{escape(title)}</b><span style="flex:1"></span>
<span>{len(pages)} form(s)</span><button onclick="window.print()">Print / Save as PDF</button></div>
{body}</body></html>"""
