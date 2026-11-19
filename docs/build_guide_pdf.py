#!/usr/bin/env python3
"""Build the client-facing PDF guide: how to use and how to run the LVAEP Tutor Hours site.

    .venv/bin/python docs/build_guide_pdf.py            # writes docs/LVAEP Tutor Hours - MVP Guide.pdf
    .venv/bin/python docs/build_guide_pdf.py --out /path/to/file.pdf

Needs reportlab (pip install reportlab). Facts that change per deployment live in CONFIG below.
"""
import argparse
import datetime as dt
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

CONFIG = {
    "site_url": "https://lvaep-tutor-portal-umber.vercel.app",
    "admin_name": "Cristhian Barcelos",
    "admin_email": "",  # pass --admin-email; the build refuses to run without it
    "support_name": "Henrique Brito Sampaio, Columbia Software Solutions",
    "support_email": "hbs9322@gmail.com",
    "repo_url": "https://github.com/HenriqueSampaio/LVAEP-Tutor-Portal",
    "date": dt.date.today().strftime("%B %-d, %Y"),
    "cron_time": "9:00 AM Eastern (8:00 AM in winter)",
    "version": "MVP 1.0",
}

NAVY = colors.HexColor("#1f3a5f")
MUTED = colors.HexColor("#5b6472")
LIGHT = colors.HexColor("#eef2f7")
RULE = colors.HexColor("#c9d2de")
WARN_BG = colors.HexColor("#fff7d6")

styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=10.5, leading=15, spaceAfter=6)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=9, leading=12.5, textColor=MUTED)
H1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY,
                    spaceBefore=6, spaceAfter=10)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13.5, leading=17, textColor=NAVY,
                    spaceBefore=14, spaceAfter=6)
H3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.black,
                    spaceBefore=10, spaceAfter=4)
TITLE = ParagraphStyle("title", parent=H1, fontSize=26, leading=31, spaceAfter=4)
SUB = ParagraphStyle("sub", parent=BODY, fontSize=12, leading=16, textColor=MUTED)
CODE = ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=9, leading=12, backColor=LIGHT,
                      borderPadding=(4, 6, 4, 6), spaceBefore=2, spaceAfter=8, leftIndent=4)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=9.5, leading=13, spaceAfter=0)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")


def P(text, style=BODY):
    return Paragraph(text, style)


def bullets(items, style=BODY):
    return ListFlowable([ListItem(P(i, style), leftIndent=12) for i in items], bulletType="bullet", start="•",
                        leftIndent=14, bulletFontSize=9, spaceAfter=6)


def steps(items, style=BODY):
    return ListFlowable([ListItem(P(i, style), leftIndent=14) for i in items], bulletType="1", leftIndent=18,
                        bulletFontName="Helvetica-Bold", bulletFontSize=10, spaceAfter=6)


def table(rows, widths, header=True):
    data = [[P(c, CELLB if (header and r == 0) else CELL) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), LIGHT))
    t.setStyle(TableStyle(style))
    t.spaceAfter = 10
    return t


def callout(text, bg=WARN_BG):
    t = Table([[P(text, BODY)]], colWidths=[6.5 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    t.spaceBefore, t.spaceAfter = 4, 10
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.9 * inch, 0.55 * inch, f"LVAEP Tutor Hours · {CONFIG['version']} · {CONFIG['date']}")
    canvas.drawRightString(letter[0] - 0.9 * inch, 0.55 * inch, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.line(0.9 * inch, 0.72 * inch, letter[0] - 0.9 * inch, 0.72 * inch)
    canvas.restoreState()


def build(out_path):
    c = CONFIG
    url = c["site_url"]
    story = []

    # ---------- cover ----------
    story += [Spacer(1, 1.2 * inch), P("LVAEP Tutor Hours", TITLE),
              P("Tutor session reporting for Literacy Volunteers of America — Essex &amp; Passaic Counties", SUB),
              Spacer(1, 0.3 * inch),
              P(f"<b>MVP guide:</b> how to use the site and how it runs", H2),
              Spacer(1, 0.15 * inch)]
    story.append(table([
        ["Site address", f'<a href="{url}" color="#1f3a5f">{url}</a>'],
        ["Prepared for", f"{c['admin_name']}, Executive Director, LVAEP"],
        ["Prepared by", c["support_name"]],
        ["Version / date", f"{c['version']} · {c['date']}"],
        ["Source code", f'<a href="{c["repo_url"]}" color="#1f3a5f">{c["repo_url"]}</a>'],
    ], [1.6 * inch, 4.9 * inch], header=False))
    story.append(callout(
        "<b>What this is.</b> A working first version (MVP) of the portal described in the CSS PRD. It replaces the "
        "per-student monthly PDF form: tutors log sessions and submit each month from a phone or computer; staff see who "
        "is missing, review or correct reports, send reminders, and print LVAEP's official <i>Student Monthly Attendance "
        "&amp; Achievement Form</i> or download spreadsheets. It starts <b>empty</b> — there is no sample data on the live "
        "site. Everything you enter is real data stored in a private database.", LIGHT))
    story.append(callout(
        "<b>Please read before entering real student names.</b> This is a test deployment for your evaluation, on free "
        "hosting plans and without automatic database backups yet. It is safe for trying the workflow with a few real "
        "or made-up records. Before LVAEP relies on it for all 52 tutors and 111 students, the items in "
        "section 6 (backups, email, hosting ownership, privacy review) need to be agreed and completed."))
    story.append(PageBreak())

    # ---------- contents ----------
    story += [P("Contents", H1), bullets([
        "1. Signing in for the first time",
        "2. Set up LVAEP's data: tutors, students, assignments (15 minutes)",
        "3. The monthly cycle: calendar, logging hours, submitting, reviewing, printing",
        "4. Reminders, email and notifications",
        "5. A 20-minute test script",
        "6. How the site runs: hosting, database, daily job, costs, security, backups",
        "7. Operating tasks: redeploying, resetting a password, running it locally",
        "8. What's not in the MVP yet, and decisions we need from LVAEP",
    ])]

    # ---------- 1. sign in ----------
    story += [P("1. Signing in for the first time", H1),
              P(f"Open <a href='{url}' color='#1f3a5f'>{url}</a> on any phone, tablet or computer. The site works best in "
                "Safari, Chrome or Edge; nothing needs to be installed."),
              steps([
                  f"Sign in with <b>{c['admin_email']}</b> and the one-time temporary password sent to you separately.",
                  "You are asked to choose your own password (at least 8 characters). The temporary one stops working.",
                  "You land on <b>Monthly reports</b>. The menu bar gives you: Monthly reports · Calendar · Students · "
                  "Tutors &amp; accounts · Reminders · Activity log. The bell icon shows notifications; the person icon "
                  "changes your password; the exit icon signs out.",
              ]),
              P("Your account is a <b>staff</b> account: it can see and change everything. Tutors get <b>tutor</b> "
                "accounts that only see their own assigned students. Up to four staff accounts (or more) can be created "
                "the same way as tutor accounts, by choosing the role <i>Staff</i>."),
              P("<b>Forgot your password?</b> Until email delivery is connected (section 4) the site can't send reset "
                "links, and the sign-in page says so. A staff member opens <b>Tutors &amp; accounts → Edit → Temporary "
                "password</b> to issue a new one. If every staff member is locked out, CSS can reset yours (section 7). "
                "After ten wrong passwords from the same place, sign-in for that address pauses for 15 minutes.")]

    # ---------- 2. set up data ----------
    story += [P("2. Set up LVAEP's data (about 15 minutes)", H1),
              P("2.1 Create tutor and staff accounts", H2),
              steps([
                  "Go to <b>Tutors &amp; accounts → Create account</b>. Enter the name, email, phone (optional), role "
                  "(Tutor or Staff) and the training hours completed so far.",
                  "The site shows a <b>temporary password once</b>. Give it to the person (phone, text, in person, or your "
                  "own email). An invitation email is also prepared; it is <i>kept on the Reminders page</i> until email "
                  "sending is connected (section 4).",
                  "At their first sign-in the person must choose their own password.",
                  "<b>Edit</b> an account to change details, mark training hours, deactivate it (history is kept, sign-in "
                  "is blocked) or issue a new temporary password.",
              ]),
              P("2.2 Add students", H2),
              steps([
                  "Go to <b>Students → Add student</b>: first and last name, program (default ESL), enrollment date, notes.",
                  "Open a student to see their tutors, this fiscal year's hours by month, and their status.",
                  "<b>Status.</b> <i>Pause</i> keeps the student but hides them from the month's reports. <i>Drop</i> asks "
                  "for a date and reason, ends all of the student's assignments and is <b>permanent</b>: only a staff "
                  "member can readmit, and the site asks for an explicit confirmation (as agreed in the kickoff meeting).",
              ]),
              P("2.3 Assign tutors to students", H2),
              steps([
                  "Open a student → <b>Assign a tutor</b>. Choose the tutor, the start date, the <b>meeting place</b> and "
                  "the usual <b>days / times</b> (these print on the official form).",
                  "The site warns, and asks you to confirm, when a tutor has fewer than 10 training hours or already has "
                  "5 students (the usual group is 3–5).",
                  "A student can have several tutors; each tutor–student pair gets its own monthly report. End an "
                  "assignment from the student page when a pair stops working together.",
              ])]

    # ---------- 3. monthly cycle ----------
    story += [P("3. The monthly cycle", H1),
              P("3.1 Calendar (optional, but it saves chasing)", H2),
              bullets([
                  "<b>Staff:</b> Calendar → pick a tutor → <b>Propose session</b> (date, start and end time, the students, "
                  "a note). The proposal is <i>Pending</i> until the tutor approves or rejects it; the tutor is notified.",
                  "<b>Tutors:</b> add their own sessions (confirmed immediately), approve or reject staff proposals under "
                  "<b>Requests</b>, and cancel with a reason. The calendar refuses two confirmed sessions that overlap.",
                  "Month, week and day views all work on a phone. After a session has happened, <b>Log hours</b> on it "
                  "opens the hours form pre-filled, so scheduling and reporting stay in step.",
                  "Scheduled sessions do <i>not</i> count as hours by themselves: the tutor still logs the hours.",
              ]),
              P("3.2 Tutors log sessions and submit the month", H2),
              bullets([
                  "<b>My students</b> shows each assigned student with this month's hours against the ~4 hours/week target "
                  "(2 tutoring + 2 homework), plus a red banner if an earlier month is still unsubmitted.",
                  "<b>Log session:</b> date, attendance (Present · Student absent · Tutor absent · Holiday/site closed · "
                  "Cancelled), tutoring hours and homework hours in quarter-hour steps (up to 8 each), and a note. Only "
                  "<i>Present</i> entries carry hours. One entry per student per day; no future dates; the date must fall "
                  "inside the assignment period.",
                  "On the student's month page the tutor also ticks <b>goals attained</b> (the official form's list, A–D, "
                  "plus an \"Other\" line and notes) and, if the student stopped, the <b>leaving date and reason</b> — "
                  "staff are notified so they can update the student's status.",
                  "<b>Submit month</b> locks the month. A second submission is refused; after that, only staff can change "
                  "or reopen it. The current month can be submitted early (with a warning); future months cannot.",
              ]),
              P("3.3 Staff review, correct and export", H2),
              bullets([
                  "<b>Monthly reports</b> lists every tutor–student pair for the month with its status (Not started · In "
                  "progress · Needs changes · Submitted · Reviewed), a completion bar, filters and search. Switch months "
                  "with the arrows.",
                  "Open a report to <b>Mark reviewed</b>, <b>Return to tutor</b> with a note (the tutor is notified and "
                  "the month reopens for them), or correct entries yourself. Every staff change is written to the "
                  "<b>Activity log</b>.",
                  "<b>Print submitted forms</b> produces LVAEP's <i>Student Monthly Attendance &amp; Achievement Form</i>, "
                  "one page per student, with each day's hours by fiscal-year month (July–June), monthly totals, goals "
                  "attained so far this year, the STOPPED box, site, days and times. Use your browser's Print → "
                  "<i>Save as PDF</i>. A single student's form prints from their report page (<b>Print form</b> or "
                  "Ctrl/Cmd+P).",
                  "<b>Summary CSV</b> (one row per report, with totals and achievements) and <b>Sessions CSV</b> (one row "
                  "per session) open in Excel or Google Sheets.",
              ])]

    # ---------- 4. reminders & email ----------
    story += [P("4. Reminders, email and notifications", H1),
              P("Every notification appears in the <b>bell</b> inside the site. Under <b>Reminders</b> staff control the "
                "automatic schedule and can send reminders by hand:"),
              bullets([
                  "<b>Last day of the month:</b> tutors who have not submitted get \"It's the last day of October — don't "
                  "forget to submit your hours\".",
                  "<b>Overdue follow-up:</b> on the 3rd, a second reminder for last month.",
                  "<b>Weekly nudge</b> (off by default): tutors who logged nothing in 7 days, on the weekday you choose.",
                  "<b>Send a reminder now</b> notifies every tutor with an unsubmitted report for the chosen month; "
                  "<b>Remind N tutors</b> on the Monthly reports page does the same. The history shows what went out.",
                  f"The automatic check runs once a day at about {c['cron_time']}; the <b>Run today's check now</b> button "
                  "runs it immediately.",
              ]),
              callout("<b>Email delivery is not connected in this MVP.</b> Invitations, password-reset links and reminder "
                      "emails are generated and listed under <b>Reminders → Recent emails</b>, where <b>Preview</b> shows "
                      "exactly what the tutor would receive. Tutors still see every reminder in the bell when they open the "
                      "site, and new tutors sign in with the temporary password you give them. Turning real sending on takes "
                      "about an hour of setup: LVAEP adds two DNS records for its email domain to a free Resend account; CSS "
                      "then switches the site over. Until then, nothing is sent to anyone.")]

    # ---------- 5. test script ----------
    story += [P("5. A 20-minute test script", H1),
              P("This walks through the whole monthly workflow with one made-up tutor and student. You need two email "
                "addresses: your own (admin) and a second one for the \"tutor\" (any address — no email is sent)."),
              steps([
                  "Sign in as admin and set your password.",
                  "<b>Tutors &amp; accounts → Create account:</b> name <i>Test Tutor</i>, your second email, role Tutor, "
                  "12 training hours. Note the temporary password.",
                  "<b>Students → Add student:</b> <i>Sample Student</i>, program ESL, enrolled last month.",
                  "Open the student → <b>Assign a tutor</b>: Test Tutor, start date the 1st of last month, meeting place "
                  "<i>Newark Public Library</i>, days/times <i>Tuesdays 6–8 pm</i>.",
                  "<b>Calendar</b> → choose Test Tutor → <b>Propose session</b> for next week.",
                  "Open a private/incognito browser window (or your phone), go to the site, sign in as Test Tutor with the "
                  "temporary password and choose a new one.",
                  "As the tutor: <b>Requests</b> → approve the proposed session. <b>My students</b> → Sample Student → "
                  "<b>Log session</b> for two dates last month (2 h tutoring + 2 h homework each), tick a goal, then use the "
                  "month switcher to go to last month and <b>Submit</b>.",
                  "Back as admin: <b>Monthly reports</b> → last month → the report shows <i>Submitted</i> with 8 hours. Open "
                  "it → <b>Return to tutor</b> with a note. As the tutor, fix a session and submit again. As admin, "
                  "<b>Mark reviewed</b>.",
                  "<b>Print submitted forms</b> → Save as PDF, and download the <b>Summary CSV</b>.",
                  "<b>Reminders</b> → <b>Send a reminder now</b> for this month; as the tutor, check the bell. Open "
                  "<b>Recent emails → Preview</b> to see the invitation and reminder emails that would have been sent.",
                  "<b>Students</b> → Sample Student → <b>Drop</b> with a reason; notice that assigning a tutor is no "
                  "longer offered. Then <b>Readmit</b> (the site asks you to confirm). Check the <b>Activity log</b>.",
              ]),
              P("Individual session entries can be deleted (by the tutor until the month is submitted, by staff any "
                "time; every deletion is logged). Students, tutors, assignments and reports are never deleted — they "
                "are paused, ended, dropped or deactivated so the history stays. CSS will clear your test records before "
                "real use, or start a fresh database.", SMALL)]

    story.append(PageBreak())

    # ---------- 6. how it runs ----------
    story += [P("6. How the site runs", H1),
              P("6.1 Architecture", H2),
              table([
                  ["Part", "What it is", "Where / who"],
                  ["Web app", "A single-page web app (plain HTML, CSS and JavaScript) served over HTTPS; no app store "
                              "install.", "Vercel (hosting), US East region"],
                  ["Server", "A small Python service (no framework) that answers the app's requests, enforces "
                             "permissions and produces the forms and CSVs. Runs as a serverless function: it starts on "
                             "demand and costs nothing when idle.", "Vercel"],
                  ["Database", "PostgreSQL holding accounts, students, assignments, sessions, reports, calendar, "
                               "notifications, the email log and the audit trail.", "Supabase, AWS us-east-1 (N. Virginia)"],
                  ["Daily job", "Once a day the host calls the site's scheduled-task address, which runs the reminder "
                                "rules and delivers any queued emails. Protected by a secret.", "Vercel Cron"],
                  ["Code", "Open repository with tests (57 automated tests run on SQLite and PostgreSQL).",
                   c["repo_url"]],
              ], [1.0 * inch, 3.7 * inch, 1.8 * inch]),
              P("6.2 Accounts, costs and ownership", H2),
              table([
                  ["Service", "Plan today", "Monthly cost today", "For real use"],
                  ["Vercel", "Hobby (CSS's account)", "$0", "Move the project to an LVAEP-owned (or CSS-managed) team; "
                                                        "Pro is $20/month per seat if needed"],
                  ["Supabase", "Free (CSS's account)", "$0", "Pro, $25/month: daily backups kept 7 days, never pauses. "
                                                          "Supabase offers nonprofit discounts on request"],
                  ["Resend (email)", "Not yet connected", "$0", "Free tier (3,000 emails/month) is enough; needs "
                                                            "LVAEP's email domain"],
                  ["Total", "", "$0", "About $25–45/month, mostly for database backups"],
              ], [1.1 * inch, 1.4 * inch, 1.1 * inch, 2.9 * inch]),
              P("The PRD says the client owns production accounts and data. Today the hosting and database accounts are "
                "CSS's, for the evaluation. At handoff they are transferred to LVAEP (or kept by CSS under a maintenance "
                "agreement) — see section 8."),
              P("6.3 Security and privacy", H2),
              bullets([
                  "All traffic is encrypted (HTTPS). Passwords are stored as salted PBKDF2 hashes, never in clear text. "
                  "Sessions use HttpOnly, Secure cookies and expire after 14 days.",
                  "Tutors can only read and write the students assigned to them; every request is checked on the server, "
                  "not just hidden in the interface. Staff can see everything. There is no public or anonymous access.",
                  "Repeated wrong passwords are throttled (after 10 failures from one place, that address waits 15 "
                  "minutes; a wider limit slows guessing from many places). Unknown and known emails answer in the same "
                  "time, so the sign-in page doesn't reveal who has an account. With a temporary password, only the "
                  "choose-your-password page works. Changing a password signs out every other device.",
                  "The database accepts connections only with its password; Supabase's public data API is disabled for "
                  "every table (row-level security on, no policies).",
                  "Every staff action that changes data (corrections, returns, drops, readmissions, account changes) is "
                  "recorded in the Activity log with who did it and when.",
                  "<b>Not yet done:</b> an independent security review, a data-retention rule, and automatic backups. "
                  "Student first and last names are the most sensitive data stored; no addresses, dates of birth or "
                  "identifiers are collected.",
              ]),
              P("6.4 Backups and what happens if something breaks", H2),
              bullets([
                  "On the free database plan there are <b>no automatic backups</b>. CSS can take a manual export at any time "
                  "(and will do so before any change to the live site). For real use, the Pro plan adds daily backups.",
                  "The free database plan pauses a project after about a week without database activity. The site's "
                  "daily job queries the database every morning, which should keep it awake; if it ever pauses, the "
                  "site shows a \"database isn't reachable\" message and CSS restores it from the dashboard in about a "
                  "minute (nothing is lost).",
                  "The hosting and database providers both publish status pages. If the site shows \"Couldn't load this "
                  "page\" or \"Something went wrong on the server\", email the support contact below.",
              ])]

    # ---------- 7. operating tasks ----------
    story += [P("7. Operating tasks (for whoever maintains the site)", H1),
              P("These are technical steps for CSS or an LVAEP IT volunteer. Nothing here is needed for day-to-day use."),
              P("7.1 Settings the live site reads (Vercel → Project → Settings → Environment Variables)", H2),
              table([
                  ["Variable", "Purpose"],
                  ["DATABASE_URL", "Supabase connection string (transaction pooler, port 6543). Secret: it is the key to "
                                   "all the data. Rotate it in Supabase → Settings → Database if it ever leaks."],
                  ["CRON_SECRET", "Random secret the daily job must present. Vercel sends it automatically."],
                  ["APP_URL", f"The site's address ({url}); used in emails and email previews."],
                  ["EMAIL_MODE", "<i>stored</i> (default on Vercel): keep emails for preview. Remove it and set "
                                 "RESEND_API_KEY, EMAIL_FROM and EMAIL_REPLY_TO to send real email."],
                  ["LVAEP_TZ", "Time zone for dates and the daily check (default America/New_York)."],
              ], [1.5 * inch, 5.0 * inch]),
              P("7.2 Redeploying after a code change", H2),
              bullets([
                  f"The project is linked to the GitHub repository {c['repo_url']}: pushing to the <b>main</b> branch "
                  "redeploys automatically; pull requests get their own preview address.",
                  "From a laptop with the Vercel CLI: <font face='Courier'>npx vercel --prod</font> in the project folder.",
                  "Run the tests first: <font face='Courier'>python3 -m unittest discover -s tests -t . -v</font>.",
              ]),
              P("7.3 Creating or recovering the administrator login", H2),
              P("From the project folder, with DATABASE_URL in <font face='Courier'>.env</font> (never commit that file):"),
              P("python3 -m venv .venv &amp;&amp; .venv/bin/pip install -r requirements.txt<br/>"
                ".venv/bin/python bootstrap_admin.py --name \"Full Name\" --email person@lvaep.org<br/>"
                ".venv/bin/python bootstrap_admin.py --email person@lvaep.org --new-password", CODE),
              P("The script prints a one-time temporary password; the person chooses their own at first sign-in. It "
                "refuses to run on a database that contains the synthetic demo data, so demo records can never end up on "
                "the live site."),
              P("7.4 Running it on a laptop (development and demos)", H2),
              P("DATABASE_URL= python3 server.py     # http://localhost:8070, SQLite with synthetic demo data<br/>"
                "python3 server.py --reset --empty   # empty local database with one admin login (SQLite)<br/>"
                "python3 -m unittest discover -s tests -t . -v   # the automated tests<br/>"
                "python3 check_setup.py              # checks the database and email settings in .env", CODE),
              P("A laptop run uses a local SQLite file in <font face='Courier'>data/</font> (demo data, emails saved "
                "as HTML files in <font face='Courier'>data/outbox/</font>) <b>only when no DATABASE_URL is set</b>. "
                "With the live DATABASE_URL in <font face='Courier'>.env</font>, <font face='Courier'>server.py</font> "
                "would connect to the live database — hence the empty <font face='Courier'>DATABASE_URL=</font> prefix "
                "above, and never load demo data into Postgres unless <font face='Courier'>--demo</font> is passed. "
                "See <font face='Courier'>README.md</font>, <font face='Courier'>docs/SETUP.md</font> and "
                "<font face='Courier'>docs/DEPLOY.md</font> in the repository.")]

    # ---------- 8. not yet / decisions ----------
    story += [P("8. What's not in the MVP yet, and decisions we need from LVAEP", H1),
              P("8.1 Not in this version", H2),
              bullets([
                  "<b>Email sending</b> (needs LVAEP's domain — about an hour once someone with DNS access is available).",
                  "<b>Text-message reminders</b>, payroll, learning plans and automatic achievement scoring (out of scope in "
                  "the PRD).",
                  "<b>Importing past months</b> from the old PDF forms (the PRD leaves this to LVAEP to decide).",
                  "<b>Deleting students, tutors, assignments or reports</b> from the interface (they are paused, ended "
                  "or deactivated instead, so history is kept; only individual session entries can be deleted, and that "
                  "is logged). CSS can purge test data.",
              ]),
              P("8.2 Assumptions built into the MVP that need your confirmation", H2),
              P("These are the open PRD decisions. Each is implemented one way so you can see it working; all are easy to "
                "change."),
              table([
                  ["Topic", "What the MVP does today", "Your call"],
                  ["Hours", "Tutoring and homework hours are entered separately and also shown combined. Only "
                            "\"Present\" sessions carry hours.", "Keep separate, or one combined number?"],
                  ["Fiscal year", "July 1 – June 30, as on the form (\"FY 2026–2027\").", "Confirm"],
                  ["One report per", "Tutor–student pair (a student with two tutors has two monthly reports).",
                   "Or one per student, merging tutors?"],
                  ["Review vs. approval", "Staff <i>review</i>: mark reviewed, return with a note, or correct directly. "
                                          "Nothing blocks on an approval.", "Is a formal approval step needed?"],
                  ["Corrections", "Tutors edit freely until they submit; afterwards only staff can change or reopen.",
                   "Should tutors have a grace period after submitting?"],
                  ["Attendance codes", "Student absent / Tutor absent / Holiday print as SA / TA / H in the day's box; "
                                       "Cancelled prints blank.", "Match your current conventions?"],
                  ["Achievements", "The form's goal list A–D, plus an \"Other\" line and free notes, ticked per month; the "
                                   "printed form shows every goal attained so far in the fiscal year.", "Confirm the list"],
                  ["Leaving", "The tutor records date and reason; staff are notified and decide the student's status. "
                              "A drop is permanent; readmission is staff-only.", "Confirm"],
                  ["Reminders", "Last day of month and overdue on the 3rd are on; weekly nudge is off.",
                   "Which should be on, and should they also go by email/text?"],
                  ["Who can be staff", "Any staff member can create accounts, assign students and review. There is one "
                                       "staff role.", "Do different staff need different rights?"],
              ], [1.15 * inch, 3.45 * inch, 1.9 * inch]),
              P("8.3 Before real use — the handoff checklist", H2),
              steps([
                  "LVAEP confirms the decisions above; CSS adjusts the MVP (small changes).",
                  "Connect email (Resend + LVAEP domain) and switch the site to sending mode; test with staff first.",
                  "Move the database to a plan with automatic backups (or agree on a manual export routine) and agree on "
                  "data retention and who may export data.",
                  "Decide account ownership (LVAEP-owned hosting/database accounts vs. CSS-managed) and the maintenance "
                  "arrangement; record the deployment approver.",
                  "Load the real tutor and student lists (CSS can import from a spreadsheet), create staff accounts, and "
                  "hand out tutor logins in training sessions.",
                  "Run one real month in parallel with the paper forms, compare totals, then switch.",
              ]),
              P("Support", H2),
              P(f"{c['support_name']} — <a href='mailto:{c['support_email']}' color='#1f3a5f'>{c['support_email']}</a>. "
                "Please send questions, bugs and change requests by email; include what you clicked and, if possible, a "
                "screenshot.")]

    doc = SimpleDocTemplate(out_path, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.9 * inch,
                            title="LVAEP Tutor Hours — MVP guide", author=c["support_name"],
                            subject="How to use and run the LVAEP Tutor Hours site")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out_path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LVAEP Tutor Hours - MVP Guide.pdf")
    p.add_argument("--out", default=default)
    for key in ("site_url", "admin_name", "admin_email", "cron_time", "version"):
        p.add_argument(f"--{key.replace('_', '-')}", dest=key)
    args = p.parse_args()
    for key in ("site_url", "admin_name", "admin_email", "cron_time", "version"):
        if getattr(args, key):
            CONFIG[key] = getattr(args, key)
    if "@" not in CONFIG["admin_email"]:
        raise SystemExit("Pass --admin-email with the administrator's real address: the guide tells them to sign in with it.")
    print(f"Building for {CONFIG['admin_name']} <{CONFIG['admin_email']}> at {CONFIG['site_url']}")
    print("Wrote", build(args.out))


if __name__ == "__main__":
    main()
