"""Tests for the printable LVAEP Student Monthly Attendance & Achievement Form.

Run from the project root:  python3 -m unittest discover -s tests -t . -v
"""
import re
import sqlite3
import unittest

from tests.test_acceptance import TMP, Client, activate, make_tutor, start_server

from app import db  # noqa: E402  (after tests.test_acceptance, which points LVAEP_DB at a temporary file)


def cell(form, month, day):
    m = re.search(rf'<td(?: class=na)? data-month={month} data-day={day}>([^<]*)</td>', form)
    assert m, f"no cell {month}/{day}"
    return m.group(1)


class PrintFormTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.base = start_server()
        cls.staff = Client(cls.base)
        cls.staff.login("staff@test.example")
        cls.tutor_a_id, temp_a = make_tutor(cls.staff, "Pat Tutor", "print-a@test.example")
        cls.tutor_b_id, temp_b = make_tutor(cls.staff, "Other Tutor", "print-b@test.example")
        cls.tutor_a, _ = activate(cls.base, "print-a@test.example", temp_a)
        cls.tutor_b, _ = activate(cls.base, "print-b@test.example", temp_b)
        _, s = cls.staff.post("/api/staff/students", {"first_name": "Alice", "last_name": "Reader", "enrolled_on": "2026-06-01"})
        cls.student = s["id"]
        status, body = cls.staff.post("/api/staff/assignments", {
            "tutor_id": cls.tutor_a_id, "student_id": cls.student, "start_date": "2026-07-01",
            "meeting_place": "Bloomfield Public Library", "schedule": "Tuesdays, 6:00–8:00 pm"})
        assert status == 200, body
        a = cls.tutor_a
        for date, att, tut, hw in (("2026-08-04", "present", 1.5, 2), ("2026-10-06", "present", 2, 2),
                                   ("2026-10-13", "student_absent", 0, 0), ("2026-10-20", "holiday", 0, 0),
                                   ("2026-10-15", "cancelled", 0, 0)):
            status, body = a.post("/api/sessions", {"student_id": cls.student, "date": date, "attendance": att,
                                                    "tutoring_hours": tut, "homework_hours": hw})
            assert status == 200, body
        report = f"/api/reports/{cls.tutor_a_id}/{cls.student}"
        a.put(f"{report}/2026-08", {"achievements": ["*Enter Employment", "Read a book (old checklist)"],
                                    "achievement_other": "Got a library card"})
        a.put(f"{report}/2026-10", {"achievements": ["Vote or register to vote"], "leaving_date": "2026-10-20",
                                    "leaving_reason": "Moved to Ohio"})

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def form(self, client, month="2026-10", tutor=None):
        status, body = client.get(f"/print?tutor={tutor or self.tutor_a_id}&student={self.student}&month={month}&fragment=1")
        self.assertEqual(status, 200, body)
        return body

    def test_01_grid_hours_codes_and_totals(self):
        f = self.form(self.tutor_a)
        self.assertTrue(f.startswith('<section class="lv-form"'))
        self.assertNotIn("<html", f)
        self.assertEqual(cell(f, "2026-10", 6), "4")  # 2 h tutoring + 2 h homework
        self.assertEqual(cell(f, "2026-08", 4), "3.5")
        self.assertEqual(cell(f, "2026-10", 13), "SA")
        self.assertEqual(cell(f, "2026-10", 20), "H")
        self.assertEqual(cell(f, "2026-10", 15), "")  # cancelled has no code on the form
        self.assertEqual(cell(f, "2026-10", "total"), "4")
        self.assertEqual(cell(f, "2026-08", "total"), "3.5")
        self.assertEqual(cell(f, "2026-11", "total"), "")  # after the month being printed
        self.assertIn("<td class=na data-month=2027-02 data-day=30>", f)  # no Feb 30
        self.assertIn("<td class=na data-month=2026-09 data-day=31>", f)
        self.assertIn("FY 2026–2027", f)
        self.assertIn("<u>Pat Tutor</u>", f)
        self.assertIn("<u>Alice Reader</u>", f)

    def test_02_goals_attained_so_far_this_year(self):
        f = self.form(self.tutor_a)
        ticked = re.findall(r"<li><span>([^<]+)</span><span class=box>&#10003;</span></li>", f)
        self.assertEqual(set(ticked), {"*Enter Employment", "Vote or register to vote"})
        self.assertIn("Got a library card; Read a book (old checklist)", f)  # E. Other(s)
        august = self.form(self.tutor_a, "2026-08")  # October's goal isn't attained yet in August
        self.assertEqual(re.findall(r"<li><span>([^<]+)</span><span class=box>&#10003;</span></li>", august),
                         ["*Enter Employment"])

    def test_03_stopped_site_days_and_times(self):
        f = self.form(self.tutor_a)
        self.assertRegex(f, r"<p><span class=box>&#10003;</span> Please place")
        self.assertIn("Moved to Ohio (last session 2026-10-20)", f)
        self.assertIn("<b>Tutoring Site:</b> Bloomfield Public Library", f)
        self.assertIn("<b>Day(s):</b> Tuesdays", f)
        self.assertIn("<b>Time(s):</b> 6:00–8:00 pm", f)
        self.assertRegex(self.form(self.tutor_a, "2026-09"), r"<p><span class=box></span> Please place")

    def test_04_access(self):
        status, _ = self.tutor_b.get(f"/print?tutor={self.tutor_a_id}&student={self.student}&month=2026-10&fragment=1")
        self.assertEqual(status, 403)
        status, _ = self.tutor_a.get("/print?month=2026-10")
        self.assertEqual(status, 403)
        self.assertIn("Pat Tutor", self.form(self.staff))  # staff print any pair
        self.assertEqual(self.tutor_a.post(f"/api/reports/{self.tutor_a_id}/{self.student}/2026-08/submit")[0], 200)
        status, page = self.staff.get("/print?month=2026-08")
        self.assertEqual(status, 200)
        self.assertIn('href="/print-form.css"', page)
        self.assertEqual(page.count('<section class="lv-form"'), 1)

    def test_05_report_api_round_trips_other(self):
        _, b = self.tutor_a.get(f"/api/reports/{self.tutor_a_id}/{self.student}/2026-08")
        self.assertEqual(b["report"]["achievement_other"], "Got a library card")
        _, meta = self.tutor_a.get("/api/meta")
        self.assertEqual([g["heading"] for g in meta["achievement_groups"]],
                         ["A. Economic", "B. Educational", "C. Family", "D. Societal/Community"])

    def test_06_old_databases_get_the_new_column(self):
        path = f"{TMP}/old.sqlite3"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE reports (id INTEGER PRIMARY KEY, tutor_id INTEGER, student_id INTEGER, month TEXT, "
                     "achievements TEXT NOT NULL DEFAULT '[]')")
        conn.execute("INSERT INTO reports (tutor_id, student_id, month) VALUES (1, 1, '2026-08')")
        conn.commit()
        conn.close()
        conn = db.connect(path)
        db.init(conn)
        self.assertEqual(conn.execute("SELECT achievement_other FROM reports").fetchone()[0], "")
        conn.close()


if __name__ == "__main__":
    unittest.main()
