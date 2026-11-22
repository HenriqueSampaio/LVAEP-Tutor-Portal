#!/usr/bin/env python3
"""Build the short client-facing PDF: a quick-start guide to using the LVAEP Tutor Hours site.

    .venv/bin/python docs/build_quick_guide_pdf.py --admin-email person@example.org
    # writes docs/LVAEP Tutor Hours - Quick Start.pdf

The full guide (how the site runs, operating tasks, open decisions) is built by build_guide_pdf.py;
this one reuses its styles and CONFIG so the two documents match.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import KeepTogether, SimpleDocTemplate, Spacer  # noqa: E402

from build_guide_pdf import (BODY, CONFIG, H1, H2, LIGHT, P, SMALL, SUB, TITLE, bullets, callout, footer,  # noqa: E402
                             steps, table)


def build(out_path):
    c = CONFIG
    url = c["site_url"]
    link = f'<a href="{url}" color="#1f3a5f">{url}</a>'
    mail = f'<a href="mailto:{c["support_email"]}" color="#1f3a5f">{c["support_email"]}</a>'
    story = []

    # ---------- heading ----------
    story += [P("LVAEP Tutor Hours", TITLE),
              P("Quick start guide for staff", SUB),
              Spacer(1, 0.12 * inch)]
    story.append(table([
        ["Site address", link],
        ["Your login", f"{c['admin_email']} (administrator)"],
        ["Prepared by", c["support_name"]],
        ["Date", c["date"]],
    ], [1.4 * inch, 5.1 * inch], header=False))
    story.append(callout(
        f"<b>Want a walkthrough?</b> We are happy to get on a call and go through the site with you, or to join your "
        f"first tutor training. Email {mail} with a few times that work for you. The same address is the place for "
        "questions and anything that looks wrong.", LIGHT))

    # ---------- 1. sign in ----------
    story.append(KeepTogether([
        P("1. Signing in", H1),
        steps([
            f"Open {link} on any phone, tablet or computer (Safari, Chrome or Edge). Nothing to install.",
            f"Enter <b>{c['admin_email']}</b> and the temporary password we sent you separately.",
            "Choose your own password (at least 8 characters). The temporary one stops working.",
            "You land on <b>Monthly reports</b>. The menu also has <b>Calendar</b>, <b>Students</b>, "
            "<b>Tutors &amp; accounts</b>, <b>Reminders</b> and <b>Activity log</b>. The bell shows notifications; the "
            "person icon changes your password; the exit icon signs out.",
        ]),
        P("Forgot a password? The site can't email reset links yet, so a staff member issues a new temporary password "
          "from <b>Tutors &amp; accounts → Edit</b>. If every staff member is locked out, email us and we reset yours.",
          SMALL),
    ]))

    # ---------- 2. set up ----------
    story.append(KeepTogether([
        P("2. Add tutors and students (about 15 minutes)", H1),
        P("Tutors", H2),
        steps([
            "<b>Tutors &amp; accounts → Create account</b>: name, email, phone (optional), role <i>Tutor</i> (or "
            "<i>Staff</i> for a colleague who should see everything), and training hours completed.",
            "The site shows a <b>temporary password once</b>. Pass it to the tutor by phone, text or in person. They "
            "choose their own password the first time they sign in.",
            "<b>Edit</b> an account to update details, deactivate it (history is kept) or issue a new temporary password.",
        ]),
    ]))
    story.append(KeepTogether([
        P("Students", H2),
        steps([
            "<b>Students → Add student</b>: first and last name, program (default ESL), enrollment date, notes.",
            "Open the student → <b>Assign a tutor</b>: choose the tutor, the start date, the <b>meeting place</b> and "
            "the usual <b>days / times</b>. These print on the official form. A student can have more than one tutor.",
            "<b>Status</b>: <i>Pause</i> is for a short break. The student stays on the tutor's list and in the month's "
            "reports, marked Paused, until you press <i>Resume</i>. <i>Drop</i> (date and reason) ends their assignments "
            "and is permanent unless a staff member readmits them, which the site asks you to confirm.",
        ]),
    ]))

    # ---------- 3. each month ----------
    story.append(KeepTogether([
        P("3. Each month", H1),
        table([
            ["Tutors", "Staff"],
            ["<b>My students</b> shows each assigned student and this month's hours against the ~4 hours/week target.",
             "<b>Monthly reports</b> lists every tutor–student pair with its status: Not started · In progress · "
             "Needs changes · Submitted · Reviewed. Use the arrows to change month."],
            ["<b>Log session</b>: date, attendance (Present · Student absent · Tutor absent · Holiday/site closed · "
             "Cancelled), tutoring hours and homework hours in quarter-hour steps, and a note. One entry per student "
             "per day; no future dates.",
             "Open a report to <b>Mark reviewed</b>, or <b>Return to tutor</b> with a note. The tutor is notified and "
             "the month reopens for them. Staff can also correct entries directly; every change is logged."],
            ["On the student's month page, open <b>Achievements this month</b> and tick the goals attained (the official "
             "form's list, plus an <b>E. Other(s)</b> box). If the student stopped, fill in <b>Did the student stop "
             "coming?</b> (date left and reason).",
             "<b>Print submitted forms</b> produces LVAEP's <i>Student Monthly Attendance &amp; Achievement Form</i>, "
             "one page per tutor–student pair (a student with two tutors gets two pages), with the fiscal year's hours by "
             "month. Use the browser's Print → Save as PDF."],
            ["<b>Submit month</b> locks the month. After that only staff can change or reopen it.",
             "<b>Summary CSV</b> (one row per report) and <b>Sessions CSV</b> (one row per session) open in Excel or "
             "Google Sheets. <b>Remind N tutors</b> nudges everyone who hasn't submitted."],
        ], [3.25 * inch, 3.25 * inch]),
    ]))

    # ---------- 4. calendar ----------
    story.append(KeepTogether([
        P("4. Calendar (optional)", H1),
        bullets([
            "<b>Staff</b>: Calendar → pick a tutor → <b>Propose session</b> (date, times, students, note). It stays "
            "<i>Pending</i> until the tutor approves or rejects it under <b>Requests</b>.",
            "<b>Tutors</b> add their own sessions, which are confirmed immediately, and can cancel with a reason. Two "
            "confirmed sessions can't overlap.",
            "After a session has happened, open it and, under <b>Log hours for the monthly report</b>, click the student's "
            "name: the hours form opens pre-filled. A scheduled session counts as hours only once the tutor logs it.",
        ]),
    ]))

    # ---------- 5. reminders ----------
    story.append(KeepTogether([
        P("5. Reminders and notifications", H1),
        bullets([
            "Every reminder appears in the <b>bell</b> inside the site. Automatic ones go to tutors who haven't "
            "submitted: on the <b>last day of the month</b> and again on the <b>3rd</b> for the previous month. A weekly "
            "nudge for tutors who logged nothing in 7 days is available under <b>Reminders</b> (off by default).",
            "<b>Send a reminder now</b> on the Reminders page notifies every tutor with an unsubmitted report for the "
            f"chosen month. The automatic check runs daily at about {c['cron_time']}; <b>Run today's check now</b> runs "
            "it immediately.",
        ]),
        callout("<b>Email isn't connected yet.</b> Invitations and reminders are prepared and listed under "
                "<b>Reminders → Recent emails</b>, where <b>Preview</b> shows what each tutor would receive. Until "
                "LVAEP's email domain is connected (about an hour of setup, on our side once you give the go-ahead), "
                "nothing is emailed: tutors see reminders in the bell, and new tutors sign in with the temporary password "
                "you give them."),
    ]))

    # ---------- 6. good to know ----------
    story.append(KeepTogether([
        P("6. Good to know", H1),
        bullets([
            "The site starts <b>empty</b>. Everything you see is what LVAEP enters; there is no sample data.",
            "Nothing is ever deleted: students are paused or dropped, assignments ended, accounts deactivated, so the "
            "history stays. Individual session entries can be removed (by the tutor until the month is submitted, by "
            "staff any time) and every removal is logged.",
            "Tutors only see their own students. Staff see everything, and every staff change is in the "
            "<b>Activity log</b>.",
            "After ten wrong passwords from the same place, sign-in for that address pauses for 15 minutes.",
            "This is an evaluation setup. If you'd rather start fresh after trying it out, we clear the records in a "
            "minute. Before LVAEP relies on it for all tutors and students, we'll agree on backups, email and hosting "
            "ownership together; the full guide covers those.",
        ]),
        P(f"Questions, problems or a walkthrough call: {mail}. Please include what you clicked and, if possible, a "
          "screenshot.", BODY),
    ]))

    doc = SimpleDocTemplate(out_path, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.9 * inch,
                            title="LVAEP Tutor Hours — Quick start guide", author=c["support_name"],
                            subject="How to use the LVAEP Tutor Hours site")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out_path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LVAEP Tutor Hours - Quick Start.pdf")
    p.add_argument("--out", default=default)
    for key in ("site_url", "admin_name", "admin_email", "cron_time", "version"):
        p.add_argument(f"--{key.replace('_', '-')}", dest=key)
    args = p.parse_args()
    for key in ("site_url", "admin_name", "admin_email", "cron_time", "version"):
        if getattr(args, key):
            CONFIG[key] = getattr(args, key)
    if "@" not in CONFIG["admin_email"]:
        raise SystemExit("Pass --admin-email with the administrator's real address: the guide tells them to sign in with it.")
    print(f"Building quick start for {CONFIG['admin_name']} <{CONFIG['admin_email']}> at {CONFIG['site_url']}")
    print("Wrote", build(args.out))


if __name__ == "__main__":
    main()
