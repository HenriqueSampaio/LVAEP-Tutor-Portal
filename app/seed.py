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
# The same slots as 24-hour clock times, for the calendar.
SLOT_TIMES = {"10:00–12:00": ("10:00", "12:00"), "1:00–3:00": ("13:00", "15:00"),
              "6:00–8:00 pm": ("18:00", "20:00"), "5:30–7:30 pm": ("17:30", "19:30")}

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

    # "E. Other(s)" goals on a couple of Maria's reports, so the printed form shows that line filled in.
    for student_idx, month, other in ((0, db.fiscal_months(this_month)[1], "Passed the DMV written test"),
                                      (1, prev_month, "Opened a savings account")):
        conn.execute("UPDATE reports SET achievement_other = ? WHERE tutor_id = ? AND student_id = ? AND month = ?",
                     (other, maria, student_ids[student_idx], month))

    seed_calendar(conn, today, holidays, tutor_ids, staff_ids, paused)

    for uid in tutor_ids:
        db.notify(conn, uid, "welcome",
                  "Welcome to LVAEP tutor reporting! Log each session here and submit each month when you're done.")
    db.notify(conn, maria, "returned",
              f"Staff reopened your {first.strftime('%B')} report for Fatima Haddad: “{returned_note}” "
              "Please fix it and submit again.",
              link=f"#/tutor/student/{student_ids[2]}?month={prev_month}")
    db.audit(conn, staff_ids[0], "seed", "Loaded synthetic demo data")
    conn.commit()


def _add_event(conn, tutor_id, date, start, end, students, created_by, status="confirmed", origin="tutor", notes="",
               **extra):
    cols = {"tutor_id": tutor_id, "date": date.isoformat(), "start_time": start, "end_time": end, "status": status,
            "origin": origin, "notes": notes, "created_by": created_by, **extra}
    cur = conn.execute(f"INSERT INTO calendar_events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                       list(cols.values()))
    conn.executemany("INSERT INTO calendar_event_students (event_id, student_id) VALUES (?, ?)",
                     [(cur.lastrowid, sid) for sid in students])
    return cur.lastrowid


def _free_slot(conn, tutor_id, date, length_min, hours=(11, 14, 16, 10, 9, 15)):
    for h in hours:
        start, end = f"{h:02d}:00", f"{h + length_min // 60:02d}:{length_min % 60:02d}"
        if not db.confirmed_overlap(conn, tutor_id, date.isoformat(), start, end):
            return start, end
    return None


def seed_calendar(conn, today, holidays, tutor_ids, staff_ids, paused):
    """Scheduled sessions: each pair's weekly slot from three weeks back to four weeks ahead, plus a few
    staff proposals for Maria and James in every approval state."""
    rng = random.Random(7)  # separate from seed()'s generator so the rest of the demo data is unchanged
    first_day, last_day = today - dt.timedelta(days=21), today + dt.timedelta(days=28)
    rows = conn.execute(
        "SELECT tutor_id, student_id, schedule, start_date, end_date FROM assignments ORDER BY tutor_id, id").fetchall()
    for r in rows:
        day_name, slot = (x.strip() for x in r["schedule"].split(",", 1))
        start, end = SLOT_TIMES[slot]
        weekday = DAYS.index(day_name[:-1])
        d = max(first_day, dt.date.fromisoformat(r["start_date"]))
        d += dt.timedelta(days=(weekday - d.weekday()) % 7)
        stop = min(last_day, dt.date.fromisoformat(r["end_date"])) if r["end_date"] else last_day
        while d <= stop:
            if d not in holidays and not (r["student_id"] == paused and d >= today - dt.timedelta(days=24)):
                same = conn.execute(
                    """SELECT id FROM calendar_events WHERE tutor_id = ? AND date = ? AND start_time = ? AND end_time = ?
                       AND status = 'confirmed'""", (r["tutor_id"], d.isoformat(), start, end)).fetchone()
                if same:  # two students in the same slot meet together
                    conn.execute("INSERT INTO calendar_event_students (event_id, student_id) VALUES (?, ?)",
                                 (same["id"], r["student_id"]))
                elif not db.confirmed_overlap(conn, r["tutor_id"], d.isoformat(), start, end):
                    note = rng.choice(["", "", "", "Bring the graded reader", "Practice for the citizenship interview",
                                       "Job application follow-up"])
                    _add_event(conn, r["tutor_id"], d, start, end, [r["student_id"]], r["tutor_id"], notes=note)
            d += dt.timedelta(days=7)

    maria, james = tutor_ids[0], tutor_ids[1]
    dana = staff_ids[0]
    proposed_at = f"{today - dt.timedelta(days=1)} 10:15:00"

    def students_of(tutor_id):
        return [r["student_id"] for r in conn.execute(
            "SELECT student_id FROM assignments WHERE tutor_id = ? AND end_date IS NULL ORDER BY id", (tutor_id,))]

    maria_students, james_students = students_of(maria), students_of(james)
    proposals = [
        (maria, today + dt.timedelta(days=2), 90, maria_students[:1], "Extra session before the library's reading fair"),
        (maria, today + dt.timedelta(days=9), 60, maria_students[1:3], "Small-group conversation practice"),
        (james, today + dt.timedelta(days=4), 90, james_students[:1], "Make-up session for the missed holiday"),
    ]
    for tutor_id, date, length, students, notes in proposals:
        slot = _free_slot(conn, tutor_id, date, length)
        if slot:
            _add_event(conn, tutor_id, date, *slot, students, dana, status="pending", origin="staff", notes=notes,
                       created_at=proposed_at)
            label = ", ".join(r["n"] for r in conn.execute(
                f"""SELECT first_name || ' ' || last_name AS n FROM students
                    WHERE id IN ({','.join('?' * len(students))})""", students))
            db.notify(conn, tutor_id, "calendar",
                      f"Dana Whitfield proposed a session: {label} on {date:%a %b} {date.day}. Please approve or reject it.",
                      link=f"#/calendar?view=week&date={date.isoformat()}")

    date = today + dt.timedelta(days=5)
    slot = _free_slot(conn, maria, date, 60, hours=(9, 10, 11))
    if slot:
        _add_event(conn, maria, date, *slot, maria_students[:1], dana, status="rejected", origin="staff",
                   notes="Morning slot at the Bloomfield office", created_at=proposed_at, responded_by=maria,
                   responded_at=f"{today} 08:40:00", response_note="I work mornings that week, sorry!")
    date = today + dt.timedelta(days=12)
    slot = _free_slot(conn, maria, date, 60, hours=(13, 14, 15))
    if slot:
        _add_event(conn, maria, date, *slot, maria_students[:1], dana, status="confirmed", origin="staff",
                   notes="Placement test practice", created_at=proposed_at, responded_by=maria,
                   responded_at=f"{today} 08:45:00")
    later = conn.execute(
        """SELECT id FROM calendar_events WHERE tutor_id = ? AND status = 'confirmed' AND origin = 'tutor' AND date > ?
           ORDER BY date LIMIT 1""", (maria, (today + dt.timedelta(days=7)).isoformat())).fetchone()
    if later:
        conn.execute("""UPDATE calendar_events SET status = 'cancelled', cancelled_by = ?, cancelled_at = ?,
                        cancel_reason = 'Student is traveling that week' WHERE id = ?""",
                     (maria, f"{today} 09:00:00", later["id"]))
