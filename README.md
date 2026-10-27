# LVAEP Tutor Hours — working prototype

A mobile-friendly tutor reporting portal for **Literacy Volunteers of America – Essex & Passaic Counties**, built by Columbia Software Solutions from *CSS PRD — LVAEP v0.2* and the client meeting notes.

It replaces the per-student monthly PDF form: tutors log sessions and submit each month; staff see who is missing, review or correct reports, send reminders, and export.

> **Prototype status.** Everything here is *Proposed* (PRD §2). All people and records in the demo data are synthetic. Items marked **Assumption** below are open PRD decisions that still need LVAEP sign-off.

## Run it

Requires only Python 3.9+ (no packages to install).

```bash
python3 server.py            # http://localhost:8070 — loads demo data on first run
python3 server.py --reset    # wipe and reload the demo data
python3 server.py --reset --empty   # empty system with one admin (admin@lvaep.example / demo1234)
python3 server.py --host 0.0.0.0    # open it from a phone on the same Wi-Fi
python3 -m unittest discover -s tests -t . -v   # acceptance, calendar and print tests (30)
```

Demo accounts (password `demo1234`): **dana@lvaep.example** (staff), **maria@tutors.example** and **james@tutors.example** (tutors). The login page has one-click buttons for them.

Set `LVAEP_TODAY=2026-10-31` to pretend it's another day (e.g. to see the last-day-of-month reminder).

## Five-minute demo script

1. **Tutor (Maria, ideally on a phone).** Home shows her students for this month with hours vs. the ~4 h/week target, plus a red “September is overdue” banner and a yellow “staff asked for a change” banner.
2. Open **Fatima Haddad → September**. Staff returned it because one session says 4 h tutoring + 0 h homework. Tap **Edit**, set 2 + 2, save, **Submit September**. The month locks.
3. Back on October, tap **Log session** on any card: date, attendance (present / student absent / tutor absent / holiday / cancelled), tutoring and homework hours, a note.
4. **Staff (Dana).** *Monthly reports* → September: status counts, completion bar, filter by status, search. Fatima's report is now *Submitted* → open it → **Mark reviewed** or **Return to tutor** with a note.
5. **Print submitted forms** gives LVAEP's *Student Monthly Attendance & Achievement Form*, one per student (days × months grid for the fiscal year, goals attained, STOPPED, site/days/times) → Print → Save as PDF. On any student's report, tutors and staff can print that student's form with **Print form** or **⌘P / Ctrl+P**. **Summary CSV** / **Sessions CSV** give spreadsheets.
6. **Remind N tutors** notifies everyone with a missing report. *Reminders* shows the automatic schedule and history.
7. *Students* → open **Hyun Park** (dropped in August) to see that a drop is permanent and only staff can readmit. Open any active student to **Assign a tutor** (warns if the tutor has under 10 training hours or already has 5 students).
8. *Tutors & accounts* → **Create account**: staff get a temporary password; the tutor must choose their own at first sign-in.
9. *Activity log*: every staff correction, return, drop and readmission.
10. **Calendar.** As Dana, open *Calendar*, pick a tutor and **Propose session**: it stays *Pending* (dashed outline) until the tutor answers. As Maria, *Requests* lists Dana's proposals: **Approve** one and **Reject** the other. Sessions Maria adds herself are confirmed at once, and the calendar refuses one that overlaps a confirmed session. On a confirmed session that has already happened, **Log hours** opens the usual log dialog pre-filled. Month, week and day views all work on a phone.

## What's built (PRD F1 + meeting notes)

| Need (source) | In the prototype |
|---|---|
| Tutor sees assigned students; enters session dates + tutoring and homework hours, per session or at month end (PRD F1) | Student cards + session log; quarter-hour steppers; works on a phone |
| Submit the month once (PRD acceptance) | Submit locks the month; a second submit is rejected |
| Staff see the correct total; another tutor cannot see the student (PRD acceptance) | Staff overview totals; every API call checks the tutor–student assignment (tests 01–02) |
| Staff assign students and review/correct (PRD F1) | Assignments, review, return-with-note, staff edits (audited) |
| Export fields: names, meeting place, days/times, dates/hours, achievements, reason/date for leaving (PRD F1) | Printable form + 2 CSVs |
| “Make export look like the current format”; form totals the whole fiscal year (meeting) | The official form, landscape on one page: each day's hours (or TA / SA / H) by fiscal-year month, monthly totals, official goals |
| Reminders on the last day of the month, maybe weekly (meeting) | Last day of month, overdue on the 3rd, optional weekly; manual send |
| Admin creates tutor accounts (meeting) | Accounts with temp password + forced change; deactivate; reset |
| Drop is permanent; readmission is admin-only (meeting) | Drop ends all assignments; readmit needs explicit confirmation |
| Students can have several tutors; 10 h training before 3–5 students (meeting) | Multiple assignments per student; assignment warnings |
| Session calendar: tutors schedule their own sessions; staff propose sessions the tutor must approve | Month / week / day calendar; pending → confirmed / rejected; cancel with reason; no overlapping confirmed sessions; group sessions; notifications both ways; staff actions audited |
| Exceptions: missing hours, duplicates, absences, holidays, stopped tutoring, corrections (PRD) | Validation + attendance codes + leaving fields + return/reopen |

## Assumptions on open PRD decisions (need client sign-off)

- **Hours:** tutoring and homework are kept **separate** and also shown combined. Only “present” entries carry hours.
- **Fiscal year:** July 1 – June 30 (the form says “FY 2026–2027”).
- **Report granularity:** one monthly report per *tutor–student pair* (a student with two tutors gets two reports).
- **Review vs. approval:** staff *review*. They can mark a report reviewed, return it to the tutor with a note, or correct it themselves (logged).
- **Correction window:** tutors edit freely until they submit; after that only staff can change or reopen it.
- **Achievements:** the official form's goals (A–D, `app/db.py` → `ACHIEVEMENT_GROUPS`) plus an “E. Other(s)” line and free-text notes, checked per month. The printed form ticks every goal attained so far in the fiscal year.
- **Printed hours:** each day's box shows tutoring + homework hours. A *cancelled* entry is left blank (the form has no code for it).
- **Leaving:** the tutor reports date + reason, and staff are notified. Only staff change the student's status (pause or permanent drop).
- **Notifications:** shown in the app only. Each one is stored with `email_status`, so email can be added once LVAEP picks a provider.
- **Month cutoff:** the current month can be submitted early (with a warning); future months cannot.
- **Calendar vs. hours:** scheduled sessions (calendar) are kept separate from logged hours (monthly report). A scheduled session doesn't count toward hours until the tutor logs it, which **Log hours** makes a one-click step.
- **Calendar permissions:** tutors cancel sessions on their own calendar; staff can withdraw their own pending proposals and cancel any session (logged). Staff can't propose sessions on past dates, but tutors can record ones that already happened. A pending proposal that overlaps a confirmed session is refused up front.

## Code map

```
server.py              entry point (flags above)
app/db.py              schema, domain rules, report bundle (totals, FY breakdown), calendar queries
app/server.py          HTTP server + JSON API, role/assignment access checks, /api/calendar routes
app/reminders.py       month-end / overdue / weekly reminder rules (run every 30 min, idempotent)
app/exports.py         CSV exports and the official attendance & achievement form
app/seed.py            synthetic demo data, generated relative to today
static/                single-page app (vanilla JS, no build step); print-form.css styles the printed form
tests/test_acceptance.py  end-to-end API tests
tests/test_calendar.py    calendar scheduling, approval and permission tests
tests/test_print.py       the printed form's grid, goals, STOPPED box and access
data/lvaep.sqlite3     created on first run (gitignore it)
```

## Not production-ready yet

Before real data goes in, see PRD §3: **HTTPS hosting**, backups, data retention, **email delivery**, password reset by email, login rate limiting, hosting/ownership decisions, and a privacy review of student data. The prototype uses PBKDF2 password hashes, HttpOnly SameSite cookies, assignment-based access checks and an audit log. It has not been security-reviewed.
