"""Email invitations, password links and notification emails.

Run from the project root:  python3 -m unittest discover -s tests -t . -v

No real email is sent: emails are saved as files (the default with no RESEND_API_KEY), or the
Resend call is replaced with a fake that records what would have been sent.
"""
import glob
import os
import re
import unittest
from unittest import mock

from tests.test_acceptance import TMP, Client, activate, make_tutor, start_server

from app import db, mailer  # noqa: E402  (imported after test_acceptance points the app at TMP)

os.environ["LVAEP_OUTBOX"] = os.path.join(TMP, "outbox")


def token_from(text):
    return re.search(r"set-password\?token=([\w-]+)", text).group(1)


class EmailTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.base = start_server()
        cls.staff = Client(cls.base)
        cls.staff.login("staff@test.example")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        os.environ.pop("RESEND_API_KEY", None)
        os.environ.pop("EMAIL_REDIRECT_TO", None)
        os.environ.pop("EMAIL_MODE", None)

    def outbox(self, kind=None):
        conn = db.connect()
        try:
            rows = conn.execute("SELECT * FROM email_outbox ORDER BY id").fetchall()
            return [dict(r) for r in rows if kind is None or r["kind"] == kind]
        finally:
            conn.close()

    def latest(self, kind, to_email):
        return [e for e in self.outbox(kind) if e["to_email"] == to_email][-1]

    def deliver(self):
        return mailer.deliver_pending()

    # ---------- invitations ----------

    def test_01_new_account_gets_invitation_that_sets_password_and_signs_in(self):
        tid, temp = make_tutor(self.staff, "Rosa Invitee", "rosa@tutors.example")
        invite = self.latest("invite", "rosa@tutors.example")
        self.assertEqual(invite["subject"], "You're invited to LVAEP Tutor Hours")
        self.assertIn("Accept invitation", invite["html"])
        token = token_from(invite["text"])

        self.deliver()  # no RESEND_API_KEY: saved as a file to look at
        files = glob.glob(os.path.join(TMP, "outbox", f"{invite['id']:05d}-invite-*.html"))
        self.assertEqual(len(files), 1)
        self.assertEqual(self.outbox("invite")[-1]["status"], "saved")

        visitor = Client(self.base)
        status, info = visitor.get(f"/api/password/link?token={token}")
        self.assertEqual((status, info["purpose"], info["email"]), (200, "invite", "rosa@tutors.example"))
        status, body = visitor.post("/api/password/link", {"token": token, "password": "short"})
        self.assertEqual(status, 400)
        status, body = visitor.post("/api/password/link", {"token": token, "password": "a-good-password"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["user"]["must_change_password"], 0)
        self.assertEqual(visitor.get("/api/me")[1]["user"]["id"], tid)  # signed in straight away

        # Single use, and the new password works.
        self.assertEqual(Client(self.base).get(f"/api/password/link?token={token}")[0], 400)
        Client(self.base).login("rosa@tutors.example", "a-good-password")
        self.assertEqual(Client(self.base).post("/api/login", {"email": "rosa@tutors.example", "password": temp})[0], 401)

    def test_02_temporary_password_still_works_as_a_fallback(self):
        _, temp = make_tutor(self.staff, "Fallback Fran", "fran@tutors.example")
        activate(self.base, "fran@tutors.example", temp)

    def test_03_staff_can_email_a_fresh_link_and_old_links_stop_working(self):
        tid, _ = make_tutor(self.staff, "Resend Ray", "ray@tutors.example")
        first = token_from(self.latest("invite", "ray@tutors.example")["text"])
        status, body = self.staff.post(f"/api/staff/tutors/{tid}/send-link")
        self.assertEqual((status, body["purpose"]), (200, "invite"))
        second = token_from(self.latest("invite", "ray@tutors.example")["text"])
        self.assertNotEqual(first, second)
        self.assertEqual(Client(self.base).get(f"/api/password/link?token={first}")[0], 400)
        self.assertEqual(Client(self.base).get(f"/api/password/link?token={second}")[0], 200)

    def test_04_tutors_cannot_use_staff_email_tools(self):
        _, temp = make_tutor(self.staff, "Nosy Ned", "ned@tutors.example")
        tutor, me = activate(self.base, "ned@tutors.example", temp)
        self.assertEqual(tutor.post(f"/api/staff/tutors/{me['id']}/send-link")[0], 403)
        self.assertEqual(tutor.get("/api/staff/emails")[0], 403)

    # ---------- forgot password ----------

    def test_05_forgot_password_emails_a_reset_link_without_revealing_accounts(self):
        _, temp = make_tutor(self.staff, "Forgetful Flo", "flo@tutors.example")
        activate(self.base, "flo@tutors.example", temp)
        before = len(self.outbox("reset"))
        anon = Client(self.base)
        self.assertEqual(anon.post("/api/password/forgot", {"email": "nobody@tutors.example"}), (200, {"ok": True}))
        self.assertEqual(len(self.outbox("reset")), before)
        self.assertEqual(anon.post("/api/password/forgot", {"email": "FLO@tutors.example"}), (200, {"ok": True}))
        reset = self.latest("reset", "flo@tutors.example")
        self.assertEqual(reset["subject"], "Reset your LVAEP Tutor Hours password")
        status, body = anon.post("/api/password/link", {"token": token_from(reset["text"]), "password": "brand-new-pass"})
        self.assertEqual(status, 200, body)
        Client(self.base).login("flo@tutors.example", "brand-new-pass")

    def test_06_reset_requests_are_rate_limited(self):
        _, temp = make_tutor(self.staff, "Spammy Sam", "sam@tutors.example")
        activate(self.base, "sam@tutors.example", temp)
        for _ in range(6):
            Client(self.base).post("/api/password/forgot", {"email": "sam@tutors.example"})
        self.assertLessEqual(len([e for e in self.outbox() if e["to_email"] == "sam@tutors.example"]), 3)

    # ---------- notification emails ----------

    def _tutor_with_student(self, name, email):
        tid, temp = make_tutor(self.staff, name, email)
        tutor, _ = activate(self.base, email, temp)
        _, s = self.staff.post("/api/staff/students", {"first_name": "Lena", "last_name": name.split()[0],
                                                        "enrolled_on": "2026-06-01"})
        status, body = self.staff.post("/api/staff/assignments", {"tutor_id": tid, "student_id": s["id"],
                                                                  "start_date": "2026-07-01"})
        assert status == 200, body
        return tid, s["id"], tutor

    def test_07_notifications_are_emailed_with_a_link_back(self):
        tid, sid, _ = self._tutor_with_student("Nora Notify", "nora@tutors.example")
        email = self.latest("assigned", "nora@tutors.example")
        self.assertEqual(email["subject"], "You've been assigned a student")
        self.assertIn("Hi Nora,", email["text"])
        self.assertIn("http://localhost:8070/", email["text"])
        self.assertEqual([e for e in self.outbox("welcome")], [])  # the invite already welcomes them

    def test_08_staff_can_turn_notification_emails_off_but_invites_still_go(self):
        self.assertEqual(self.staff.put("/api/staff/reminders/settings", {"email_notifications": "0"})[0], 200)
        try:
            before = len(self.outbox())
            tid, sid, _ = self._tutor_with_student("Quiet Quinn", "quinn@tutors.example")
            kinds = [e["kind"] for e in self.outbox()[before:]]
            self.assertEqual(kinds, ["invite"])
        finally:
            self.staff.put("/api/staff/reminders/settings", {"email_notifications": "1"})

    # ---------- delivery ----------

    def test_09_resend_delivery_test_addresses_and_redirect(self):
        os.environ["RESEND_API_KEY"] = "re_test_fake"
        sent = []

        def fake_send(to_email, to_name, subject, html_body, text_body):
            sent.append((to_email, subject))
            return f"msg_{len(sent)}"

        with mock.patch.object(mailer, "_send_resend", side_effect=fake_send):
            make_tutor(self.staff, "Real Person", "real.person@gmail.com")
            make_tutor(self.staff, "Fake Person", "fake.person@tutors.example")
            self.deliver()
            self.assertEqual([s[0] for s in sent], ["real.person@gmail.com"])
            self.assertEqual(self.latest("invite", "fake.person@tutors.example")["status"], "skipped")
            self.assertEqual(self.latest("invite", "real.person@gmail.com")["status"], "sent")

            os.environ["EMAIL_REDIRECT_TO"] = "me@my-inbox.org"
            make_tutor(self.staff, "Redirected Rita", "rita@tutors.example")
            self.deliver()
            self.assertEqual(sent[-1], ("me@my-inbox.org", "[for rita@tutors.example] You're invited to LVAEP Tutor Hours"))

    def test_10_failed_sends_are_retried(self):
        os.environ["RESEND_API_KEY"] = "re_test_fake"
        with mock.patch.object(mailer, "_send_resend", side_effect=RuntimeError("Resend 500: try later")):
            make_tutor(self.staff, "Retry Ruth", "ruth@example-school.org")
            self.deliver()
        row = self.latest("invite", "ruth@example-school.org")
        self.assertEqual((row["status"], row["attempts"]), ("failed", 1))
        self.assertIn("try later", row["last_error"])
        with mock.patch.object(mailer, "_send_resend", return_value="msg_ok"):
            self.deliver()
        self.assertEqual(self.latest("invite", "ruth@example-school.org")["status"], "sent")

    def test_11_staff_see_the_email_log(self):
        status, body = self.staff.get("/api/staff/emails")
        self.assertEqual(status, 200)
        self.assertIn(body["status"]["mode"], ("outbox", "resend", "off"))
        self.assertTrue(body["items"])
        self.assertNotIn("html", body["items"][0])  # bodies (with links) aren't sent to the browser


if __name__ == "__main__":
    unittest.main()
