"""End-to-end API tests for the LVAEP prototype.

Run from the project root:  python3 -m unittest discover -s tests -v

Each test class starts a real server on a free port against a throwaway database, with
"today" pinned via LVAEP_TODAY so month boundaries are deterministic.
"""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

TMP = tempfile.mkdtemp(prefix="lvaep-test-")
os.environ["LVAEP_DB"] = os.path.join(TMP, "test.sqlite3")
os.environ["LVAEP_TODAY"] = "2026-10-21"
os.environ["LVAEP_QUIET"] = "1"

from app import db, reminders, seed  # noqa: E402
from app.server import serve  # noqa: E402


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req) as res:
                raw = res.read().decode()
                return res.status, (json.loads(raw) if "json" in res.headers.get("Content-Type", "") else raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body=None):
        return self.call("POST", path, body if body is not None else {})

    def put(self, path, body):
        return self.call("PUT", path, body)

    def delete(self, path):
        return self.call("DELETE", path)

    def login(self, email, password=seed.DEMO_PASSWORD):
        status, body = self.post("/api/login", {"email": email, "password": password})
        assert status == 200, body
        return body["user"]


def start_server():
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db.DB_PATH + suffix):
            os.remove(db.DB_PATH + suffix)
    conn = db.connect()
    db.init(conn)
    conn.execute("INSERT INTO users (name, email, role, password_hash) VALUES ('Staff One', 'staff@test.example', 'staff', ?)",
                 (db.hash_password(seed.DEMO_PASSWORD),))
    conn.commit()
    conn.close()
    httpd = serve("127.0.0.1", 0, scheduler=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def make_tutor(staff, name, email, training=12):
    status, body = staff.post("/api/staff/tutors", {"name": name, "email": email, "training_hours": training})
    assert status == 200, body
    return body["id"], body["temp_password"]


def activate(base, email, temp):
    c = Client(base)
    user = c.login(email, temp)
    assert user["must_change_password"] == 1
    status, _ = c.post("/api/me/password", {"current": temp, "new": seed.DEMO_PASSWORD})
    assert status == 200
    return c, user


class AcceptanceTest(unittest.TestCase):
    """PRD F1 acceptance check plus the exception rules around it."""

    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.base = start_server()
        cls.staff = Client(cls.base)
        cls.staff.login("staff@test.example")
        cls.tutor_a_id, temp_a = make_tutor(cls.staff, "Tutor A", "a@test.example")
        cls.tutor_b_id, temp_b = make_tutor(cls.staff, "Tutor B", "b@test.example")
        cls.tutor_a, _ = activate(cls.base, "a@test.example", temp_a)
        cls.tutor_b, _ = activate(cls.base, "b@test.example", temp_b)
        _, s = cls.staff.post("/api/staff/students", {"first_name": "Sam", "last_name": "Student", "enrolled_on": "2026-06-01"})
        cls.student = s["id"]
        _, s2 = cls.staff.post("/api/staff/students", {"first_name": "Other", "last_name": "Learner", "enrolled_on": "2026-06-01"})
        cls.student_b = s2["id"]
        status, body = cls.staff.post("/api/staff/assignments", {
            "tutor_id": cls.tutor_a_id, "student_id": cls.student, "start_date": "2026-07-01",
            "meeting_place": "Main library", "schedule": "Tuesdays, 6–8 pm"})
        assert status == 200, body
        status, body = cls.staff.post("/api/staff/assignments", {
            "tutor_id": cls.tutor_b_id, "student_id": cls.student_b, "start_date": "2026-07-01"})
        assert status == 200, body

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def log(self, client, date, tut=2, hw=2, attendance="present", student=None, **extra):
        return client.post("/api/sessions", {"student_id": student or self.student, "date": date,
                                              "attendance": attendance, "tutoring_hours": tut, "homework_hours": hw, **extra})

    def report(self, client, month, tutor=None, student=None):
        return client.get(f"/api/reports/{tutor or self.tutor_a_id}/{student or self.student}/{month}")

    # --- The PRD acceptance check ---

    def test_01_enter_submit_once_staff_sees_total(self):
        for date, tut, hw in [("2026-09-01", 2, 2), ("2026-09-08", 2, 1.5), ("2026-09-15", 1.5, 2)]:
            status, body = self.log(self.tutor_a, date, tut, hw)
            self.assertEqual(status, 200, body)
        self.assertEqual(self.log(self.tutor_a, "2026-09-22", attendance="student_absent")[0], 200)

        status, b = self.report(self.tutor_a, "2026-09")
        self.assertEqual(b["totals"], {"entries": 4, "attended": 3, "tutoring": 5.5, "homework": 5.5, "total": 11.0})
        self.assertEqual(b["report"]["status"], "in_progress")

        status, b = self.tutor_a.post(f"/api/reports/{self.tutor_a_id}/{self.student}/2026-09/submit")
        self.assertEqual(status, 200, b)
        self.assertEqual(b["report"]["status"], "submitted")
        status, b = self.tutor_a.post(f"/api/reports/{self.tutor_a_id}/{self.student}/2026-09/submit")
        self.assertEqual(status, 409, "a month can only be submitted once")

        status, ov = self.staff.get("/api/staff/overview?month=2026-09")
        row = next(r for r in ov["rows"] if r["student_id"] == self.student)
        self.assertEqual(row["status"], "submitted")
        self.assertEqual(row["totals"]["total"], 11.0)
        self.assertEqual(row["totals"]["tutoring"], 5.5)
        self.assertEqual(ov["submitted_hours"], 11.0)

    def test_02_other_tutor_cannot_see_student(self):
        self.assertEqual(self.report(self.tutor_b, "2026-09")[0], 403)
        self.assertEqual(self.report(self.tutor_b, "2026-09", tutor=self.tutor_b_id)[0], 403)
        self.assertEqual(self.log(self.tutor_b, "2026-10-06")[0], 403)
        status, home = self.tutor_b.get("/api/tutor/home?month=2026-09")
        self.assertNotIn(self.student, [s["student_id"] for s in home["students"]])
        self.assertEqual(self.tutor_b.get(f"/print?month=2026-09&tutor={self.tutor_a_id}&student={self.student}")[0], 403)
        _, own = self.tutor_a.get("/api/reports/%d/%d/2026-09" % (self.tutor_a_id, self.student))
        session_id = own["sessions"][0]["id"]
        self.assertEqual(self.tutor_b.put(f"/api/sessions/{session_id}", {"date": "2026-09-01", "attendance": "present",
                                                                          "tutoring_hours": 8})[0], 403)

    def test_03_tutors_blocked_from_staff_pages(self):
        for path in ["/api/staff/overview", "/api/staff/students", "/api/staff/tutors", "/export/summary.csv?month=2026-09"]:
            self.assertEqual(self.tutor_a.get(path)[0], 403, path)
        self.assertEqual(Client(self.base).get("/api/tutor/home")[0], 401)

    # --- Corrections ---

    def test_04_submitted_month_locked_until_staff_returns_it(self):
        self.assertEqual(self.log(self.tutor_a, "2026-09-29")[0], 409)
        _, b = self.report(self.tutor_a, "2026-09")
        sid = b["sessions"][0]["id"]
        self.assertEqual(self.tutor_a.delete(f"/api/sessions/{sid}")[0], 409)

        status, b = self.staff.post(f"/api/reports/{self.tutor_a_id}/{self.student}/2026-09/return", {"note": "Check Sep 8"})
        self.assertEqual(b["report"]["status"], "returned")
        _, notes = self.tutor_a.get("/api/notifications")
        self.assertTrue(any("Check Sep 8" in n["message"] for n in notes["items"]))

        status, _ = self.tutor_a.put(f"/api/sessions/{sid}", {"date": "2026-09-01", "attendance": "present",
                                                             "tutoring_hours": 2, "homework_hours": 2.5})
        self.assertEqual(status, 200)
        _, b = self.tutor_a.post(f"/api/reports/{self.tutor_a_id}/{self.student}/2026-09/submit")
        self.assertEqual((b["report"]["status"], b["totals"]["total"]), ("submitted", 11.5))
        _, b = self.staff.post(f"/api/reports/{self.tutor_a_id}/{self.student}/2026-09/review")
        self.assertEqual(b["report"]["status"], "reviewed")
        self.assertEqual(b["report"]["reviewed_by"], "Staff One")

    def test_05_staff_corrections_are_audited(self):
        _, b = self.report(self.staff, "2026-09")
        sid = b["sessions"][0]["id"]
        status, _ = self.staff.put(f"/api/sessions/{sid}", {"date": "2026-09-01", "attendance": "present",
                                                           "tutoring_hours": 2, "homework_hours": 2})
        self.assertEqual(status, 200)
        _, log = self.staff.get("/api/staff/activity")
        self.assertTrue(any(a["action"] == "session.edit" and "Tutor A" in a["detail"] for a in log["items"]))

    # --- Session validation (PRD exceptions) ---

    def test_06_session_validation(self):
        cases = [
            ({"date": "2026-10-30"}, 400, "future"),
            ({"date": "2026-06-30"}, 400, "outside assignment"),
            ({"date": "2026-10-06", "tut": 9}, 400, "over 8 hours"),
            ({"date": "2026-10-06", "tut": 1.1}, 400, "not a quarter hour"),
            ({"date": "2026-10-06", "tut": 0, "hw": 0}, 400, "present with no hours"),
            ({"date": "bad"}, 400, "bad date"),
        ]
        for kw, expected, why in cases:
            status, body = self.log(self.tutor_a, kw["date"], kw.get("tut", 2), kw.get("hw", 2))
            self.assertEqual(status, expected, f"{why}: {body}")
        self.assertEqual(self.log(self.tutor_a, "2026-10-06")[0], 200)
        status, body = self.log(self.tutor_a, "2026-10-06")
        self.assertEqual(status, 409, "duplicate date")
        self.assertIn("session_id", body)
        status, _ = self.log(self.tutor_a, "2026-10-13", tut=2, hw=2, attendance="holiday")
        _, b = self.report(self.tutor_a, "2026-10")
        holiday = next(s for s in b["sessions"] if s["date"] == "2026-10-13")
        self.assertEqual((holiday["tutoring_hours"], holiday["homework_hours"]), (0, 0), "non-attended entries carry no hours")

    def test_07_cannot_submit_empty_or_future_month(self):
        self.assertEqual(self.tutor_b.post(f"/api/reports/{self.tutor_b_id}/{self.student_b}/2026-09/submit")[0], 400)
        self.assertEqual(self.tutor_b.post(f"/api/reports/{self.tutor_b_id}/{self.student_b}/2026-11/submit")[0], 400)

    # --- Fiscal year & exports ---

    def test_08_fiscal_year_totals_and_exports(self):
        self.assertEqual(self.log(self.tutor_a, "2026-07-14", 2, 2)[0], 200)
        _, b = self.report(self.staff, "2026-10")
        self.assertEqual(b["fiscal"]["label"], "FY 2026–2027")
        months = {m["month"]: m["total"] for m in b["fiscal"]["months"]}
        self.assertEqual(months["2026-07"], 4.0)
        self.assertEqual(months["2026-09"], 11.0)
        self.assertEqual(b["fiscal"]["totals"]["total"], 4.0 + 11.0 + b["totals"]["total"])

        status, csv_text = self.staff.get("/export/summary.csv?month=2026-09")
        self.assertEqual(status, 200)
        line = next(l for l in csv_text.splitlines() if "Sam Student" in l)
        self.assertIn(",reviewed,", line)
        self.assertIn(",11.0,", line)
        status, page = self.staff.get(f"/print?month=2026-09&tutor={self.tutor_a_id}&student={self.student}")
        self.assertIn("Student Monthly Attendance &amp; Achievement Form", page)
        self.assertIn("Sam Student", page)
        self.assertIn("Main library", page)

    def test_09_leaving_report_notifies_staff(self):
        _, s = self.staff.post("/api/staff/students", {"first_name": "Lee", "last_name": "Leaver"})
        self.staff.post("/api/staff/assignments", {"tutor_id": self.tutor_b_id, "student_id": s["id"], "start_date": "2026-08-01"})
        self.log(self.tutor_b, "2026-09-03", student=s["id"])
        self.tutor_b.put(f"/api/reports/{self.tutor_b_id}/{s['id']}/2026-09",
                         {"leaving_date": "2026-09-03", "leaving_reason": "New job hours", "achievements": ["Got a job or a better job"]})
        self.tutor_b.post(f"/api/reports/{self.tutor_b_id}/{s['id']}/2026-09/submit")
        _, notes = self.staff.get("/api/notifications")
        self.assertTrue(any("Lee Leaver" in n["message"] and "New job hours" in n["message"] for n in notes["items"]))

    # --- Students & assignments (admin-only operations) ---

    def test_10_drop_is_permanent_until_admin_readmits(self):
        _, s = self.staff.post("/api/staff/students", {"first_name": "Dee", "last_name": "Dropped"})
        sid = s["id"]
        self.staff.post("/api/staff/assignments", {"tutor_id": self.tutor_b_id, "student_id": sid, "start_date": "2026-10-01"})
        self.assertEqual(self.tutor_b.post(f"/api/staff/students/{sid}/status", {"status": "dropped"})[0], 403)
        status, _ = self.staff.post(f"/api/staff/students/{sid}/status", {"status": "dropped", "date": "2026-10-15", "reason": "Moved"})
        self.assertEqual(status, 200)
        _, detail = self.staff.get(f"/api/staff/students/{sid}")
        self.assertEqual(detail["assignments"][0]["end_date"], "2026-10-15")
        self.assertEqual(self.staff.post("/api/staff/assignments", {"tutor_id": self.tutor_b_id, "student_id": sid,
                                                                    "start_date": "2026-10-20"})[0], 409)
        self.assertEqual(self.staff.post(f"/api/staff/students/{sid}/status", {"status": "active"})[0], 409)
        self.assertEqual(self.staff.post(f"/api/staff/students/{sid}/status", {"status": "active", "readmit": True})[0], 200)

    def test_11_assignment_warnings_need_confirmation(self):
        trainee_id, _ = make_tutor(self.staff, "Trainee", "trainee@test.example", training=6)
        _, s = self.staff.post("/api/staff/students", {"first_name": "New", "last_name": "Learner"})
        body = {"tutor_id": trainee_id, "student_id": s["id"], "start_date": "2026-10-20"}
        status, resp = self.staff.post("/api/staff/assignments", body)
        self.assertEqual(status, 422)
        self.assertTrue(resp.get("needs_confirm"))
        self.assertEqual(self.staff.post("/api/staff/assignments", {**body, "confirm": True})[0], 200)
        self.assertEqual(self.staff.post("/api/staff/assignments", {**body, "confirm": True})[0], 409, "duplicate pairing")

    def test_12_deactivated_account_cannot_sign_in(self):
        uid, temp = make_tutor(self.staff, "Leaving Tutor", "gone@test.example")
        c = Client(self.base)
        c.login("gone@test.example", temp)
        self.staff.put(f"/api/staff/tutors/{uid}", {"name": "Leaving Tutor", "email": "gone@test.example", "active": False})
        self.assertEqual(c.get("/api/me")[0], 401, "existing sessions are revoked")
        self.assertEqual(Client(self.base).post("/api/login", {"email": "gone@test.example", "password": temp})[0], 403)


class ReminderTest(unittest.TestCase):
    def setUp(self):
        self.httpd, self.base = start_server()
        self.staff = Client(self.base)
        self.staff.login("staff@test.example")
        self.tutor_id, _ = make_tutor(self.staff, "Rem Tutor", "rem@test.example")
        _, s = self.staff.post("/api/staff/students", {"first_name": "Rita", "last_name": "Reader"})
        self.staff.post("/api/staff/assignments", {"tutor_id": self.tutor_id, "student_id": s["id"], "start_date": "2026-09-01"})

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def reminders_for_tutor(self, conn):
        return conn.execute("SELECT kind, message FROM notifications WHERE user_id = ? AND kind NOT IN ('welcome', 'assigned')",
                            (self.tutor_id,)).fetchall()

    def test_month_end_and_overdue_fire_once(self):
        import datetime as dt
        conn = db.connect()
        self.assertEqual(reminders.run_scheduled(conn, dt.date(2026, 10, 30)), [("overdue", 1)])
        self.assertEqual(reminders.run_scheduled(conn, dt.date(2026, 10, 31)), [("month_end", 1)])
        self.assertEqual(reminders.run_scheduled(conn, dt.date(2026, 10, 31)), [], "idempotent")
        kinds = [r["kind"] for r in self.reminders_for_tutor(conn)]
        self.assertEqual(sorted(kinds), ["month_end", "overdue"])
        self.assertIn("last day of October", self.reminders_for_tutor(conn)[-1]["message"])
        conn.close()

    def test_manual_reminder_from_staff(self):
        status, body = self.staff.post("/api/staff/reminders/send", {"month": "2026-10"})
        self.assertEqual((status, body["recipients"]), (200, 1))


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
