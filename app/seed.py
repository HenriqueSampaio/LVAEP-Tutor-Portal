"""Synthetic demo data. No real LVAEP tutors or students — every name here is made up.

Dates are generated relative to today so the demo always shows a closed previous month
(mostly submitted, a few missing) and the current month in progress.
"""
import datetime as dt
import json
import random

from . import db

DEMO_PASSWORD = "demo1234"

STAFF = [("Dana Whitfield", "dana@lvaep.example"), ("Marcus Lee", "marcus@lvaep.example")]

# name, email, phone, training hours
TUTORS = [
    ("Maria Santos", "maria@tutors.example", "973-555-0101", 12),
    ("James Okoro", "james@tutors.example", "973-555-0102", 10),
    ("Linda Chen", "linda@tutors.example", "973-555-0103", 14),
    ("Robert Diaz", "robert@tutors.example", "973-555-0104", 10),
    ("Priya Nair", "priya@tutors.example", "973-555-0105", 11),
    ("Tom Becker", "tom@tutors.example", "973-555-0106", 10),
    ("Grace Kim", "grace@tutors.example", "973-555-0107", 16),
    ("Samuel Adeyemi", "samuel@tutors.example", "973-555-0108", 10),
    ("Olivia Grant", "olivia@tutors.example", "973-555-0109", 6),  # still in training: no students yet
]

STUDENTS = [
    ("Ana", "Rivera", "ESL"), ("Wei", "Zhang", "ESL"), ("Fatima", "Haddad", "ESL"), ("Jean", "Baptiste", "ESL"),
    ("Luis", "Moreno", "ESL"), ("Tanisha", "Brooks", "Basic Literacy"), ("Dmitri", "Volkov", "ESL"),
    ("Kwame", "Mensah", "Basic Literacy"), ("Rosa", "Gutierrez", "ESL"), ("Aisha", "Bello", "ESL"),
    ("Hector", "Ramos", "Basic Literacy"), ("Mei", "Lin", "ESL"), ("Omar", "Farouk", "ESL"),
    ("Grace", "Owusu", "Basic Literacy"), ("Carlos", "Mendes", "ESL"), ("Yuki", "Tanaka", "ESL"),
    ("Denise", "Carter", "Basic Literacy"), ("Ibrahim", "Diallo", "ESL"), ("Sofia", "Petrova", "ESL"),
    ("Marcus", "Hill", "Basic Literacy"), ("Leila", "Nasser", "ESL"), ("Pedro", "Alves", "ESL"),
    ("Nadia", "Rahman", "ESL"), ("Victor", "Okafor", "Basic Literacy"), ("Elena", "Cruz", "ESL"),
    ("Hyun", "Park", "ESL"),
]

PLACES = ["Newark Public Library – Main", "Paterson Free Public Library", "LVAEP office, Bloomfield",
          "Online (Zoom)", "Montclair Public Library", "Clifton Public Library", "Passaic Public Library"]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
TIMES = ["10:00–12:00", "1:00–3:00", "6:00–8:00 pm", "5:30–7:30 pm"]

# tutor index -> list of student indexes
ASSIGN = {
    0: [0, 1, 2, 25],  # Maria: student 25 dropped in August (assignment ended)
    1: [2, 3, 4],      # James shares Fatima Haddad with Maria
    2: [5, 6, 7, 8],
    3: [9, 10, 11],
    4: [12, 13, 14, 15],
    5: [16, 17, 18],
    6: [19, 20, 21, 22],
    7: [23, 24],
}


def us_holidays(year):
    def nth(month, weekday, n):
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)

    def last(month, weekday):
        d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
        return d - dt.timedelta(days=(d.weekday() - weekday) % 7)

    return {dt.date(year, 7, 3), dt.date(year, 7, 4), nth(9, 0, 1), nth(10, 0, 2), dt.date(year, 11, 11),
            nth(11, 3, 4), nth(11, 3, 4) + dt.timedelta(days=1), dt.date(year, 12, 24), dt.date(year, 12, 25),
            dt.date(year, 1, 1), nth(1, 0, 3), nth(2, 0, 3), last(5, 0), dt.date(year, 6, 19)}


def seed(conn):
    rng = random.Random(42)
    today = db.today()
    this_month = today.strftime("%Y-%m")
    fy_start = db.fiscal_year_start(this_month)
    prev_month = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    holidays = us_holidays(fy_start.year) | us_holidays(fy_start.year + 1)
    pw = db.hash_password(DEMO_PASSWORD)

    staff_ids = []
    for name, email in STAFF:
        cur = conn.execute("INSERT INTO users (name, email, role, password_hash, training_hours) VALUES (?, ?, 'staff', ?, 0)",
                           (name, email, pw))
        staff_ids.append(cur.lastrowid)
    tutor_ids = []
    for name, email, phone, hours in TUTORS:
        cur = conn.execute(
            "INSERT INTO users (name, email, phone, role, password_hash, training_hours) VALUES (?, ?, ?, 'tutor', ?, ?)",
            (name, email, phone, pw, hours))
        tutor_ids.append(cur.lastrowid)
    student_ids = []
    for i, (first, last, program) in enumerate(STUDENTS):
        enrolled = fy_start - dt.timedelta(days=rng.randint(30, 600))
        cur = conn.execute("INSERT INTO students (first_name, last_name, program, enrolled_on) VALUES (?, ?, ?, ?)",
                           (first, last, program, enrolled.isoformat()))
        student_ids.append(cur.lastrowid)

    dropped = student_ids[25]
    drop_date = dt.date(fy_start.year, 8, 20)
    paused = student_ids[17]

    pairs = []
    for t_idx, s_idxs in ASSIGN.items():
        for s_idx in s_idxs:
            weekday = rng.randrange(6)
            start = fy_start - dt.timedelta(days=rng.randint(0, 200))
            if s_idx in (24, 15):
                start = today.replace(day=1) - dt.timedelta(days=40)  # newer pairings
            end = drop_date if student_ids[s_idx] == dropped else None
            schedule = f"{DAYS[weekday]}s, {rng.choice(TIMES)}"
            place = rng.choice(PLACES)
            conn.execute(
                "INSERT INTO assignments (tutor_id, student_id, meeting_place, schedule, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)",
                (tutor_ids[t_idx], student_ids[s_idx], place, schedule, start.isoformat(), end and end.isoformat()))
            pairs.append((tutor_ids[t_idx], student_ids[s_idx], weekday, start, end))

    conn.execute("UPDATE students SET status = 'dropped', left_on = ?, leave_reason = ? WHERE id = ?",
                 (drop_date.isoformat(), "Moved out of state for work", dropped))
    conn.execute("UPDATE students SET status = 'paused', notes = 'On leave — family travel; expected back next month' WHERE id = ?",
                 (paused,))

    # Sessions: one per week on the pair's meeting day, from the fiscal year start until today.
    for tutor_id, student_id, weekday, start, end in pairs:
        d = max(start, fy_start)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7)
        stop = min(end or today, today)
        while d <= stop:
            if student_id == paused and d >= today - dt.timedelta(days=24):
                break
            if d in holidays:
                att, tut, hw = "holiday", 0, 0
            else:
                roll = rng.random()
                att = "present" if roll < 0.86 else "student_absent" if roll < 0.95 else "tutor_absent"
                tut = rng.choice([2, 2, 2, 1.5]) if att == "present" else 0
                hw = rng.choice([2, 2, 1.5, 2.5, 1, 2]) if att == "present" else 0
            note = ""
            if att == "present" and rng.random() < 0.15:
                note = rng.choice(["Practiced reading a lease agreement", "Worked on job application",
                                   "Phonics review — short vowels", "Conversation practice: doctor visit",
                                   "Read chapter 3 of a graded reader"])
            conn.execute(
                """INSERT INTO sessions (tutor_id, student_id, date, attendance, tutoring_hours, homework_hours, note, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tutor_id, student_id, d.isoformat(), att, tut, hw, note, tutor_id))
            d += dt.timedelta(days=7)

    # Monthly reports for closed months.
    maria, james = tutor_ids[0], tutor_ids[1]
    leave_unsubmitted = {(maria, student_ids[1]), (tutor_ids[3], student_ids[10]), (tutor_ids[6], student_ids[21])}
    not_started = {(tutor_ids[5], student_ids[16])}
    returned = {(maria, student_ids[2])}
    for tutor_id, student_id, weekday, start, end in pairs:
        m = db.fiscal_months(this_month)[0]
        while m < this_month:
            first, last = db.month_bounds(m)
            if start <= last and (end is None or end >= first):
                key = (tutor_id, student_id)
                if m == prev_month and key in not_started:
                    conn.execute("DELETE FROM sessions WHERE tutor_id = ? AND student_id = ? AND date BETWEEN ? AND ?",
                                 (tutor_id, student_id, first.isoformat(), last.isoformat()))
                elif m == prev_month and key in leave_unsubmitted:
                    conn.execute("INSERT INTO reports (tutor_id, student_id, month) VALUES (?, ?, ?)", (tutor_id, student_id, m))
                else:
                    achievements = rng.sample(db.ACHIEVEMENTS, rng.choice([0, 0, 1, 1, 2]))
                    submitted = (last + dt.timedelta(days=rng.randint(0, 6))).isoformat() + f" {rng.randint(8, 21):02d}:{rng.randint(0, 59):02d}:00"
                    status = "reviewed" if m != prev_month or rng.random() < 0.4 else "submitted"
                    leaving_date = leaving_reason = None
                    if student_id == dropped and end and first <= end <= last:
                        leaving_date, leaving_reason = drop_date.isoformat(), "Moved out of state for work"
                    conn.execute(
                        """INSERT INTO reports (tutor_id, student_id, month, status, achievements, achievement_notes,
                               leaving_date, leaving_reason, submitted_at, reviewed_at, reviewed_by)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (tutor_id, student_id, m, status, json.dumps(achievements),
                         "Great progress this month." if achievements else "", leaving_date, leaving_reason or "",
                         submitted, submitted if status == "reviewed" else None,
                         staff_ids[0] if status == "reviewed" else None))
            y, mo = (int(x) for x in m.split("-"))
            m = f"{y + mo // 12:04d}-{mo % 12 + 1:02d}"
        conn.execute("INSERT OR IGNORE INTO reports (tutor_id, student_id, month) VALUES (?, ?, ?)",
                     (tutor_id, student_id, this_month))

    # The "returned" example: staff spotted one session logged as 4 h tutoring + 0 h homework.
    first, last = db.month_bounds(prev_month)
    for tutor_id, student_id in returned:
        conn.execute(
            """UPDATE sessions SET attendance = 'present', tutoring_hours = 2, homework_hours = 2
               WHERE tutor_id = ? AND student_id = ? AND attendance != 'holiday' AND date BETWEEN ? AND ?""",
            (tutor_id, student_id, first.isoformat(), last.isoformat()))
        row = conn.execute(
            """SELECT id, date FROM sessions WHERE tutor_id = ? AND student_id = ? AND attendance = 'present'
               AND date BETWEEN ? AND ? ORDER BY date LIMIT 1 OFFSET 1""", (tutor_id, student_id, first.isoformat(), last.isoformat())).fetchone()
        conn.execute("UPDATE sessions SET tutoring_hours = 4, homework_hours = 0 WHERE id = ?", (row["id"],))
        d = dt.date.fromisoformat(row["date"])
        returned_note = (f"The session on {d:%b} {d.day} shows 4 h of tutoring "
                         "and 0 h homework — should that be 2 h + 2 h?")
        conn.execute(
            """UPDATE reports SET status = 'draft', returned = 1, reviewed_at = NULL, reviewed_by = NULL, staff_note = ?
               WHERE tutor_id = ? AND student_id = ? AND month = ?""", (returned_note, tutor_id, student_id, prev_month))

    for uid in tutor_ids:
        db.notify(conn, uid, "welcome",
                  "Welcome to LVAEP tutor reporting! Log each session here and submit each month when you're done.")
    db.notify(conn, maria, "returned",
              f"Staff reopened your {first.strftime('%B')} report for Fatima Haddad: “{returned_note}” "
              "Please fix it and submit again.",
              link=f"#/tutor/student/{student_ids[2]}?month={prev_month}")
    db.audit(conn, staff_ids[0], "seed", "Loaded synthetic demo data")
    conn.commit()
