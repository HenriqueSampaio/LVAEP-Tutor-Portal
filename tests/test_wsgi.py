"""The WSGI entry point used on Vercel (app/wsgi.py) and the behaviours that only matter on a
serverless host: Secure cookies behind HTTPS, the daily cron endpoint, "stored" email with staff
preview, inline email delivery, the sign-in throttle, and the bootstrap_admin.py script.

Run from the project root:  python3 -m unittest discover -s tests -t . -v
"""
import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from wsgiref.util import setup_testing_defaults

from tests.test_acceptance import TMP, start_server  # noqa: F401  (points the app at a temp database)

from app import db, mailer, seed, server, wsgi  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(method, path, body=None, headers=None, cookie=None):
    """Drive the WSGI app directly (no sockets), the way Vercel's runtime does."""
    environ = {}
    setup_testing_defaults(environ)
    p, _, q = path.partition("?")
    environ.update({"REQUEST_METHOD": method, "PATH_INFO": p, "QUERY_STRING": q})
    data = json.dumps(body).encode() if body is not None else b""
    environ["wsgi.input"] = io.BytesIO(data)
    if body is not None:
        environ["CONTENT_TYPE"], environ["CONTENT_LENGTH"] = "application/json", str(len(data))
    for k, v in (headers or {}).items():
        environ["HTTP_" + k.upper().replace("-", "_")] = v
    if cookie:
        environ["HTTP_COOKIE"] = f"{server.COOKIE}={cookie}"
    out = {}

    def start_response(status, response_headers):
        out["status"], out["headers"] = int(status.split()[0]), response_headers

    raw = b"".join(wsgi.app(environ, start_response))
    ctype = dict(out["headers"]).get("Content-Type", "")
    return out["status"], (json.loads(raw) if "json" in ctype and raw else raw.decode()), dict(out["headers"])


def login(email, password=seed.DEMO_PASSWORD, **kw):
    status, body, headers = call("POST", "/api/login", {"email": email, "password": password}, **kw)
    assert status == 200, body
    return headers["Set-Cookie"].split(";")[0].split("=", 1)[1], headers["Set-Cookie"]


class WsgiTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd, _ = start_server()  # fresh database with one staff account; the socket server is unused
        cls.staff_cookie, _ = login("staff@test.example")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_01_static_files_and_spa_fallback(self):
        status, body, headers = call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("<title>LVAEP Tutor Hours</title>", body)
        self.assertIn("text/javascript", call("GET", "/app.js")[2]["Content-Type"])
        self.assertIn("text/css", call("GET", "/print-form.css")[2]["Content-Type"])
        self.assertIn("<title>LVAEP Tutor Hours</title>", call("GET", "/some/deep/link")[1])  # SPA fallback
        self.assertIn("<title>LVAEP Tutor Hours</title>", call("GET", "/../server.py")[1])  # no traversal
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_02_meta_hides_demo_accounts_unless_demo_data_is_loaded(self):
        status, meta, _ = call("GET", "/api/meta")
        self.assertEqual((status, meta["demo"]), (200, False))
        self.assertEqual(call("GET", "/api/me")[0], 401)
        self.assertEqual(call("GET", "/api/me", cookie=self.staff_cookie)[1]["user"]["email"], "staff@test.example")

    def test_03_session_cookie_is_secure_only_behind_https(self):
        _, plain = login("staff@test.example")
        self.assertIn("HttpOnly", plain)
        self.assertNotIn("Secure", plain)
        _, https = login("staff@test.example", headers={"X-Forwarded-Proto": "https"})
        self.assertIn("; Secure", https)
        with mock.patch.dict(os.environ, {"LVAEP_SECURE_COOKIES": "1"}):
            self.assertIn("; Secure", login("staff@test.example")[1])

    def test_04_cron_endpoint_needs_the_secret(self):
        with mock.patch.dict(os.environ, {"CRON_SECRET": ""}):
            self.assertEqual(call("GET", "/api/cron/daily")[0], 401)  # no secret configured: always refused
        with mock.patch.dict(os.environ, {"CRON_SECRET": "s3cret"}):
            self.assertEqual(call("GET", "/api/cron/daily")[0], 401)
            self.assertEqual(call("GET", "/api/cron/daily", headers={"Authorization": "Bearer wrong"})[0], 401)
            status, body, _ = call("GET", "/api/cron/daily", headers={"Authorization": "Bearer s3cret"})
        self.assertEqual(status, 200, body)
        self.assertEqual(set(body), {"ran_at", "today", "reminders", "emails_handled"})
        self.assertEqual(body["today"], os.environ["LVAEP_TODAY"])

    def test_05_stored_email_mode_delivers_inline_and_staff_can_preview_without_live_links(self):
        with mock.patch.dict(os.environ, {"EMAIL_MODE": "stored"}), mock.patch.object(server, "INLINE_MAIL", True):
            status, body, _ = call("POST", "/api/staff/tutors", {"name": "Serverless Sue", "email": "sue@tutors.example",
                                                                  "training_hours": 12}, cookie=self.staff_cookie)
            self.assertEqual(status, 200, body)
            self.assertEqual(body["email"]["mode"], "stored")
            status, log, _ = call("GET", "/api/staff/emails", cookie=self.staff_cookie)
        invite = [e for e in log["items"] if e["to_email"] == "sue@tutors.example" and e["kind"] == "invite"][0]
        self.assertEqual(invite["status"], "saved")  # handled at the end of the request, no worker thread
        self.assertNotIn("html", invite)
        conn = db.connect()
        stored = conn.execute("SELECT html, text FROM email_outbox WHERE id = ?", (invite["id"],)).fetchone()
        conn.close()
        self.assertNotRegex(stored["html"] + stored["text"], r"token=[A-Za-z0-9_-]{20,}")  # no working link kept in the database
        status, page, headers = call("GET", f"/api/staff/emails/{invite['id']}/preview", cookie=self.staff_cookie)
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("Accept invitation", page)
        self.assertIn("sue@tutors.example", page)
        self.assertNotRegex(page, r"token=[A-Za-z0-9_-]{20,}")  # the preview is not a usable sign-in link
        self.assertEqual(call("GET", f"/api/staff/emails/{invite['id']}/preview")[0], 401)
        # The temporary password still works, so staff can onboard tutors before email is connected.
        tutor_cookie, _ = login("sue@tutors.example", body["temp_password"])
        self.assertEqual(call("GET", f"/api/staff/emails/{invite['id']}/preview", cookie=tutor_cookie)[0], 403)

    def test_06_bad_requests_are_handled(self):
        self.assertEqual(call("GET", "/api/nope")[0], 404)
        self.assertEqual(call("POST", "/api/login", ["not", "an", "object"])[0], 400)
        status, body, _ = call("GET", "/api/me", headers={"Cookie": "malformed;;=;"})
        self.assertEqual(status, 401)

    def test_07_sign_in_is_throttled_per_email(self):
        status, body, _ = call("POST", "/api/staff/tutors", {"name": "Throttle Tom", "email": "tom@tutors.example",
                                                              "training_hours": 12}, cookie=self.staff_cookie)
        self.assertEqual(status, 200, body)
        temp = body["temp_password"]
        for _ in range(server.LOGIN_MAX_FAILURES):
            self.assertEqual(call("POST", "/api/login", {"email": "tom@tutors.example", "password": "wrong"})[0], 401)
        status, err, _ = call("POST", "/api/login", {"email": "tom@tutors.example", "password": temp})
        self.assertEqual(status, 429)
        self.assertIn("Too many", err["error"])
        # Other accounts are unaffected.
        login("staff@test.example")

    def test_08_local_time_is_lvaep_time(self):
        from zoneinfo import ZoneInfo
        expected = dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)
        self.assertLess(abs((db.now() - expected).total_seconds()), 5)
        self.assertRegex(db.now_iso(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_09_head_requests_mirror_get_without_a_body(self):
        status, body, headers = call("HEAD", "/")
        self.assertEqual((status, body), (200, ""))
        self.assertIn("text/html", headers["Content-Type"])
        self.assertGreater(int(headers["Content-Length"]), 100)
        status, body, headers = call("HEAD", "/api/meta")
        self.assertEqual((status, body), (200, ""))
        self.assertIn("json", headers["Content-Type"])

    def test_10_cron_rejects_odd_secrets_cleanly(self):
        with mock.patch.dict(os.environ, {"CRON_SECRET": "s3cret"}):
            self.assertEqual(call("GET", "/api/cron/daily", headers={"Authorization": "Bearer s\xe9cret"})[0], 401)

    def test_11_temporary_password_only_opens_the_password_page(self):
        status, body, _ = call("POST", "/api/staff/tutors", {"name": "Temp Tina", "email": "tina@tutors.example",
                                                              "training_hours": 12}, cookie=self.staff_cookie)
        self.assertEqual(status, 200, body)
        temp = body["temp_password"]
        cookie, _ = login("tina@tutors.example", temp)
        status, err, _ = call("GET", "/api/tutor/home", cookie=cookie)
        self.assertEqual((status, err.get("must_change_password")), (403, True))
        self.assertEqual(call("GET", "/api/calendar?start=2026-10-01&end=2026-10-31", cookie=cookie)[0], 403)
        self.assertEqual(call("GET", "/api/me", cookie=cookie)[0], 200)
        self.assertEqual(call("POST", "/api/me/password", {"current": temp, "new": "tina-new-pass"}, cookie=cookie)[0], 200)
        self.assertEqual(call("GET", "/api/tutor/home", cookie=cookie)[0], 200)

    def test_12_login_input_is_validated_before_anything_is_recorded(self):
        def audit_rows():
            conn = db.connect()
            try:
                return conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]
            finally:
                conn.close()
        before = audit_rows()
        self.assertEqual(call("POST", "/api/login", {"email": ["x"], "password": "y"})[0], 400)
        self.assertEqual(call("POST", "/api/login", {"email": "a" * 300 + "@x.example", "password": "y"})[0], 400)
        self.assertEqual(call("POST", "/api/login", {"email": "no-at-sign", "password": "y"})[0], 400)
        self.assertEqual(call("POST", "/api/login", {"email": "x@y.example", "password": 5})[0], 400)
        self.assertEqual(audit_rows(), before)
        self.assertEqual(call("POST", "/api/login", {"email": "ghost@y.example", "password": "nope"})[0], 401)
        self.assertEqual(audit_rows(), before + 1)
        # Failed sign-ins are kept but don't clutter the staff Activity log.
        status, log, _ = call("GET", "/api/staff/activity", cookie=self.staff_cookie)
        self.assertEqual(status, 200)
        self.assertFalse([i for i in log["items"] if i["action"] == "login.failed"])

    def test_13_changing_the_password_signs_out_other_devices(self):
        _, body, _ = call("POST", "/api/staff/tutors", {"name": "Library Lou", "email": "lou@tutors.example",
                                                         "training_hours": 12}, cookie=self.staff_cookie)
        temp = body["temp_password"]
        c1, _ = login("lou@tutors.example", temp)
        self.assertEqual(call("POST", "/api/me/password", {"current": temp, "new": "lou-first-pass"}, cookie=c1)[0], 200)
        c2, _ = login("lou@tutors.example", "lou-first-pass")
        self.assertEqual(call("GET", "/api/me", cookie=c2)[0], 200)
        self.assertEqual(call("POST", "/api/me/password", {"current": "lou-first-pass", "new": "lou-second-pass"},
                              cookie=c1)[0], 200)
        self.assertEqual(call("GET", "/api/me", cookie=c1)[0], 200)  # the device that changed it stays signed in
        self.assertEqual(call("GET", "/api/me", cookie=c2)[0], 401)  # the other (shared library computer) is out

    def test_14_tutors_cannot_learn_other_students_names_from_calendar_errors(self):
        _, owner, _ = call("POST", "/api/staff/tutors", {"name": "Owner Olga", "email": "olga@tutors.example",
                                                          "training_hours": 12}, cookie=self.staff_cookie)
        _, nosy, _ = call("POST", "/api/staff/tutors", {"name": "Nosy Nick", "email": "nick@tutors.example",
                                                         "training_hours": 12}, cookie=self.staff_cookie)
        _, student, _ = call("POST", "/api/staff/students", {"first_name": "Secret", "last_name": "Surname",
                                                              "enrolled_on": "2026-06-01"}, cookie=self.staff_cookie)
        status, body, _ = call("POST", "/api/staff/assignments", {"tutor_id": owner["id"], "student_id": student["id"],
                                                                   "start_date": "2026-07-01"}, cookie=self.staff_cookie)
        self.assertEqual(status, 200, body)
        nick, _ = login("nick@tutors.example", nosy["temp_password"])
        call("POST", "/api/me/password", {"current": nosy["temp_password"], "new": "nick-pass-123"}, cookie=nick)
        event = {"date": os.environ["LVAEP_TODAY"], "start_time": "10:00", "end_time": "11:00"}
        status, err, _ = call("POST", "/api/calendar", {**event, "student_ids": [student["id"]]}, cookie=nick)
        self.assertEqual(status, 400)
        self.assertNotIn("Secret", err["error"])
        self.assertNotIn("Surname", err["error"])
        status2, err2, _ = call("POST", "/api/calendar", {**event, "student_ids": [999999]}, cookie=nick)
        self.assertEqual((status2, err2["error"]), (400, err["error"]))  # "not yours" and "doesn't exist" look the same

    def test_15_csv_cells_cannot_run_as_spreadsheet_formulas(self):
        from app import exports
        self.assertEqual(exports._cell('=HYPERLINK("http://evil.example")'), "'=HYPERLINK(\"http://evil.example\")")
        self.assertEqual(exports._cell("+1"), "'+1")
        self.assertEqual(exports._cell("-5 min late"), "'-5 min late")
        self.assertEqual(exports._cell("@cmd"), "'@cmd")
        self.assertEqual(exports._cell("normal note"), "normal note")
        self.assertEqual(exports._cell(2.5), 2.5)
        self.assertEqual(exports._cell("a\x00b\tc"), "abc")

    def test_16_automatic_reminders_fire_once_even_when_called_twice(self):
        from app import reminders
        conn = db.connect()
        try:
            month = os.environ["LVAEP_TODAY"][:7]
            reminders.send_month_reminders(conn, month, "month_end")
            second = reminders.send_month_reminders(conn, month, "month_end")
            runs = conn.execute("SELECT COUNT(*) AS c FROM reminder_runs WHERE kind = 'month_end' AND period_key = ? "
                                "AND triggered_by IS NULL", (month,)).fetchone()["c"]
        finally:
            conn.close()
        self.assertEqual((second, runs), (0, 1))

    def test_17_init_dedupes_old_duplicate_reminder_runs_before_building_the_unique_index(self):
        conn = db.connect()
        try:
            conn.execute("DROP INDEX IF EXISTS idx_reminder_runs_auto")
            for _ in range(2):
                conn.execute("INSERT INTO reminder_runs (kind, period_key, recipients, triggered_by) VALUES ('month_end', '2020-01', 3, NULL)")
            conn.commit()
            db.init(conn)  # must not fail: keeps one row and recreates the index
            rows = conn.execute("SELECT COUNT(*) AS c FROM reminder_runs WHERE period_key = '2020-01'").fetchone()["c"]
            idx = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_reminder_runs_auto'").fetchone()
        finally:
            conn.close()
        self.assertEqual(rows, 1)
        self.assertIsNotNone(idx)


class BootstrapAdminTest(unittest.TestCase):
    """bootstrap_admin.py is how the live site gets its first (real) login."""

    def run_script(self, *args, demo=False):
        env = {**os.environ, "LVAEP_DB": self.db_path, "DATABASE_URL": ""}
        return subprocess.run([sys.executable, os.path.join(ROOT, "bootstrap_admin.py"), *args],
                              cwd=ROOT, env=env, capture_output=True, text=True)

    def setUp(self):
        self.db_path = os.path.join(tempfile.mkdtemp(prefix="lvaep-bootstrap-"), "boot.sqlite3")

    def test_creates_admin_then_resets_password_and_refuses_demo_databases(self):
        r = self.run_script("--name", "Cristhian Barcelos", "--email", "director@test.example")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Created staff account for Cristhian Barcelos", r.stdout)
        temp = r.stdout.strip().splitlines()[-1].strip()
        self.assertRegex(temp, r"^[0-9a-f]{6}-[0-9a-f]{6}-[0-9a-f]{6}$")

        conn = db.connect(self.db_path)
        u = conn.execute("SELECT * FROM users WHERE email = 'director@test.example'").fetchone()
        self.assertEqual((u["role"], u["must_change_password"]), ("staff", 1))
        self.assertTrue(db.check_password(temp, u["password_hash"]))
        self.assertEqual(conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"], 0)  # no demo data
        conn.close()

        r = self.run_script("--name", "Again", "--email", "director@test.example")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already has an account", r.stderr)

        r = self.run_script("--email", "director@test.example", "--new-password")
        self.assertEqual(r.returncode, 0, r.stderr)
        new_temp = r.stdout.strip().splitlines()[-1].strip()
        self.assertNotEqual(new_temp, temp)
        conn = db.connect(self.db_path)
        u = conn.execute("SELECT * FROM users WHERE email = 'director@test.example'").fetchone()
        self.assertTrue(db.check_password(new_temp, u["password_hash"]))
        db.audit(conn, None, "seed", "pretend demo data was loaded")
        conn.commit()
        conn.close()
        r = self.run_script("--name", "X", "--email", "x@test.example")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("demo data", r.stderr)


if __name__ == "__main__":
    unittest.main()
