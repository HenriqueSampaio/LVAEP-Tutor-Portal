"""End-to-end API tests for the tutor session calendar (scheduling, approvals, permissions).

Run from the project root:  python3 -m unittest discover -s tests -t . -v
"""
import unittest

from tests.test_acceptance import Client, activate, make_tutor, start_server

DAY = "2026-10-27"  # a Tuesday after the pinned "today" (2026-10-21)


class CalendarTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.base = start_server()
        cls.staff = Client(cls.base)
        cls.staff.login("staff@test.example")
        cls.tutor_a_id, temp_a = make_tutor(cls.staff, "Tutor A", "cal-a@test.example")
        cls.tutor_b_id, temp_b = make_tutor(cls.staff, "Tutor B", "cal-b@test.example")
        cls.tutor_a, _ = activate(cls.base, "cal-a@test.example", temp_a)
        cls.tutor_b, _ = activate(cls.base, "cal-b@test.example", temp_b)
        ids = []
        for first in ("Ana", "Ben", "Cy"):
            _, s = cls.staff.post("/api/staff/students", {"first_name": first, "last_name": "Learner",
                                                          "enrolled_on": "2026-06-01"})
            ids.append(s["id"])
        cls.s1, cls.s2, cls.s_b = ids
        for tutor, student in ((cls.tutor_a_id, cls.s1), (cls.tutor_a_id, cls.s2), (cls.tutor_b_id, cls.s_b)):
            status, body = cls.staff.post("/api/staff/assignments", {"tutor_id": tutor, "student_id": student,
                                                                     "start_date": "2026-07-01"})
            assert status == 200, body

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def create(self, client, date=DAY, start="10:00", end="11:00", students=None, **extra):
        return client.post("/api/calendar", {"date": date, "start_time": start, "end_time": end,
                                             "student_ids": students or [self.s1], **extra})

    def propose(self, date=DAY, start="10:00", end="11:00", students=None, tutor=None, **extra):
        return self.create(self.staff, date, start, end, students, tutor_id=tutor or self.tutor_a_id, **extra)

    def week(self, client, tutor=None, start="2026-10-25", end="2026-10-31"):
        q = f"/api/calendar?start={start}&end={end}" + (f"&tutor_id={tutor}" if tutor else "")
        status, body = client.get(q)
        self.assertEqual(status, 200, body)
        return {e["id"]: e for e in body["events"]}

    def test_01_tutor_created_session_is_confirmed(self):
        status, body = self.create(self.tutor_a, "2026-10-26", "09:00", "10:30", [self.s1, self.s2], notes="Unit 4")
        self.assertEqual(status, 200, body)
        ev = body["event"]
        self.assertEqual((ev["status"], ev["origin"], ev["tutor_id"]), ("confirmed", "tutor", self.tutor_a_id))
        self.assertEqual({s["id"] for s in ev["students"]}, {self.s1, self.s2})
        self.assertIn("edit", ev["actions"])
        self.assertIn(ev["id"], self.week(self.tutor_a))
        self.assertIn(ev["id"], self.week(self.staff, self.tutor_a_id))

    def test_02_staff_proposal_pending_until_tutor_approves(self):
        status, body = self.propose("2026-10-28", "14:00", "15:00", notes="Try the new workbook")
        self.assertEqual(status, 200, body)
        ev = body["event"]
        self.assertEqual((ev["status"], ev["origin"]), ("pending", "staff"))
        _, me = self.tutor_a.get("/api/me")
        self.assertGreaterEqual(me["pending_requests"], 1)
        _, req = self.tutor_a.get("/api/calendar/requests")
        mine = {e["id"]: e for e in req["events"]}
        self.assertEqual(set(mine[ev["id"]]["actions"]), {"approve", "reject"})
        _, notes = self.tutor_a.get("/api/notifications")
        self.assertTrue(any("proposed a session" in n["message"] for n in notes["items"]))

        status, body = self.tutor_a.post(f"/api/calendar/{ev['id']}/approve")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["event"]["status"], "confirmed")
        _, req = self.staff.get("/api/calendar/requests")
        self.assertEqual({e["id"]: e["status"] for e in req["events"]}[ev["id"]], "confirmed")
        status, _ = self.tutor_a.post(f"/api/calendar/{ev['id']}/approve")
        self.assertEqual(status, 409)

    def test_03_reject_marks_rejected(self):
        _, body = self.propose("2026-10-29", "16:00", "17:00")
        status, body = self.tutor_a.post(f"/api/calendar/{body['event']['id']}/reject", {"note": "I work late Thursdays"})
        self.assertEqual(status, 200, body)
        ev = body["event"]
        self.assertEqual((ev["status"], ev["response_note"], ev["actions"]), ("rejected", "I work late Thursdays", []))
        _, req = self.tutor_a.get("/api/calendar/requests")
        self.assertNotIn(ev["id"], [e["id"] for e in req["events"]])

    def test_04_tutors_cannot_touch_another_tutors_calendar(self):
        _, body = self.create(self.tutor_a, "2026-10-30", "09:00", "10:00")
        ev_id = body["event"]["id"]
        _, body = self.propose("2026-10-30", "11:00", "12:00")
        pending_id = body["event"]["id"]
        self.assertEqual(self.tutor_b.get(f"/api/calendar?start=2026-10-25&end=2026-10-31&tutor_id={self.tutor_a_id}")[0], 403)
        self.assertNotIn(ev_id, self.week(self.tutor_b))
        self.assertEqual(self.create(self.tutor_b, tutor_id=self.tutor_a_id)[0], 403)
        self.assertEqual(self.create(self.tutor_b, students=[self.s1])[0], 400)  # not B's student
        self.assertEqual(self.tutor_b.put(f"/api/calendar/{ev_id}", {"date": DAY, "start_time": "09:00",
                                                                     "end_time": "10:00", "student_ids": [self.s_b]})[0], 403)
        self.assertEqual(self.tutor_b.post(f"/api/calendar/{ev_id}/cancel")[0], 403)
        self.assertEqual(self.tutor_b.post(f"/api/calendar/{pending_id}/approve")[0], 403)
        self.assertEqual(self.tutor_b.get(f"/api/calendar/students?tutor_id={self.tutor_a_id}")[0], 403)
        # Staff propose; only the tutor decides.
        self.assertEqual(self.staff.post(f"/api/calendar/{pending_id}/approve")[0], 403)
        self.assertEqual(self.staff.post(f"/api/calendar/{pending_id}/reject")[0], 403)
        self.assertEqual(self.tutor_a.post("/api/calendar/999999/cancel")[1]["error"], "Session not found.")

    def test_05_validation(self):
        status, body = self.tutor_a.post("/api/calendar", {"date": DAY, "student_ids": [self.s1]})
        self.assertEqual(status, 400)
        self.assertIn("start_time", body["error"])
        self.assertEqual(self.create(self.tutor_a, start="9am")[0], 400)
        self.assertEqual(self.create(self.tutor_a, start="11:00", end="11:00")[1]["error"],
                         "The end time must be after the start time.")
        self.assertEqual(self.create(self.tutor_a, start="12:00", end="11:00")[0], 400)
        self.assertEqual(self.tutor_a.post("/api/calendar", {"date": DAY, "start_time": "08:00", "end_time": "09:00",
                                                             "student_ids": []})[1]["error"], "Choose at least one student.")
        self.assertEqual(self.create(self.tutor_a, date="2026-02-30")[0], 400)
        self.assertEqual(self.create(self.tutor_a, date="2026-06-15")[0], 400)  # before the assignment started
        self.assertEqual(self.propose(date="2026-10-20")[1]["error"], "Staff can't propose sessions on a past date.")
        self.assertEqual(self.staff.post("/api/calendar", {"date": DAY, "start_time": "08:00", "end_time": "09:00",
                                                           "student_ids": [self.s1]})[1]["error"], "Choose a tutor.")
        # Tutors may record a session that already happened.
        self.assertEqual(self.create(self.tutor_a, date="2026-10-19", start="18:00", end="19:00")[0], 200)

    def test_06_no_overlapping_confirmed_sessions(self):
        day = "2026-11-03"
        status, body = self.create(self.tutor_a, day, "18:00", "20:00")
        self.assertEqual(status, 200, body)
        status, body = self.create(self.tutor_a, day, "19:30", "20:30", [self.s2])
        self.assertEqual(status, 409)
        self.assertIn("overlaps a confirmed session", body["error"])
        self.assertEqual(self.create(self.tutor_a, day, "20:00", "21:00")[0], 200)  # touching is fine
        self.assertEqual(self.propose(day, "17:00", "18:30")[0], 409)
        # Two overlapping proposals can both wait; the second approval is refused.
        _, p1 = self.propose(day, "10:00", "11:00")
        _, p2 = self.propose(day, "10:30", "11:30")
        self.assertEqual(self.tutor_a.post(f"/api/calendar/{p1['event']['id']}/approve")[0], 200)
        status, body = self.tutor_a.post(f"/api/calendar/{p2['event']['id']}/approve")
        self.assertEqual(status, 409)
        self.assertEqual(body["conflict_id"], p1["event"]["id"])
        # Moving a confirmed session onto another is refused too.
        _, c = self.create(self.tutor_a, day, "13:00", "14:00")
        status, _ = self.tutor_a.put(f"/api/calendar/{c['event']['id']}", {
            "date": day, "start_time": "10:15", "end_time": "11:15", "student_ids": [self.s1]})
        self.assertEqual(status, 409)

    def test_07_cancelling(self):
        day = "2026-11-04"
        _, own = self.create(self.tutor_a, day, "09:00", "10:00")
        status, body = self.tutor_a.post(f"/api/calendar/{own['event']['id']}/cancel", {"reason": "Sick"})
        self.assertEqual(status, 200, body)
        self.assertEqual((body["event"]["status"], body["event"]["cancel_reason"]), ("cancelled", "Sick"))
        self.assertEqual(self.tutor_a.post(f"/api/calendar/{own['event']['id']}/cancel")[0], 409)
        self.assertEqual(self.create(self.tutor_a, day, "09:00", "10:00")[0], 200)  # the slot is free again

        _, prop = self.propose(day, "12:00", "13:00")
        self.assertEqual(self.tutor_a.post(f"/api/calendar/{prop['event']['id']}/cancel")[0], 409)  # reject instead
        status, body = self.staff.post(f"/api/calendar/{prop['event']['id']}/cancel")
        self.assertEqual((status, body["event"]["status"]), (200, "cancelled"))

        _, conf = self.create(self.tutor_a, day, "15:00", "16:00")
        status, _ = self.staff.post(f"/api/calendar/{conf['event']['id']}/cancel", {"reason": "Site closed"})
        self.assertEqual(status, 200)
        _, log = self.staff.get("/api/staff/activity")
        actions = [r["action"] for r in log["items"]]
        self.assertIn("calendar.cancel", actions)
        self.assertIn("calendar.withdraw", actions)

        _, rej = self.propose(day, "17:00", "18:00")
        self.tutor_a.post(f"/api/calendar/{rej['event']['id']}/reject")
        self.assertEqual(self.staff.post(f"/api/calendar/{rej['event']['id']}/cancel")[0], 409)

    def test_08_editing_rules(self):
        day = "2026-11-05"
        _, prop = self.propose(day, "10:00", "11:00")
        pid = prop["event"]["id"]
        body = {"date": day, "start_time": "10:30", "end_time": "11:30", "student_ids": [self.s1, self.s2]}
        self.assertEqual(self.tutor_a.put(f"/api/calendar/{pid}", body)[0], 409)  # tutor approves, not edits
        status, res = self.staff.put(f"/api/calendar/{pid}", body)
        self.assertEqual(status, 200, res)
        self.assertEqual((res["event"]["status"], res["event"]["start_time"], len(res["event"]["students"])),
                         ("pending", "10:30", 2))
        self.tutor_a.post(f"/api/calendar/{pid}/approve")
        self.assertEqual(self.staff.put(f"/api/calendar/{pid}", body)[0], 403)  # confirmed now: tutor's to change

    def test_09_range_and_all_tutors(self):
        self.assertEqual(self.tutor_a.get("/api/calendar?start=2026-10-01&end=2026-12-31")[0], 400)
        self.assertEqual(self.tutor_a.get("/api/calendar?start=2026-10-31&end=2026-10-01")[0], 400)
        self.assertEqual(self.tutor_a.get("/api/calendar?start=2026-10-01&end=2026-10-31&tutor_id=all")[0], 403)
        self.assertEqual(self.staff.get("/api/calendar?start=2026-10-01&end=2026-10-31")[0], 400)
        _, b_ev = self.create(self.tutor_b, "2026-10-26", "09:00", "10:00", [self.s_b])
        everyone = self.week(self.staff, "all")
        self.assertIn(b_ev["event"]["id"], everyone)
        self.assertTrue(any(e["tutor_id"] == self.tutor_a_id for e in everyone.values()))

    def test_10_log_hours_only_offered_once_the_day_has_come(self):
        _, past = self.create(self.tutor_a, "2026-10-14", "18:00", "19:00")
        _, future = self.create(self.tutor_a, "2026-11-10", "18:00", "19:00")
        self.assertIn("log_hours", past["event"]["actions"])
        self.assertNotIn("log_hours", future["event"]["actions"])
        _, students = self.tutor_a.get("/api/calendar/students?date=2026-10-14")
        self.assertEqual({s["id"] for s in students["items"]}, {self.s1, self.s2})


if __name__ == "__main__":
    unittest.main()
