"""Email: invitations, password links and notification emails.

Every email is first written to the email_outbox table, in the same transaction as the thing
that caused it (so a failed request never sends a stray email). A background thread then
delivers queued emails and retries failures.

Delivery depends on the environment:
    RESEND_API_KEY set        -> sent through Resend (https://resend.com)
    no key (the default)      -> written as .html files to data/outbox/ so you can open them
    EMAIL_MODE=off            -> nothing is sent or written

Other settings:
    EMAIL_FROM          sender, e.g. "LVAEP Tutor Hours <hours@mail.lvaep.org>"
    EMAIL_REPLY_TO      where replies go (e.g. LVAEP's office address)
    APP_URL             the site's public address, used in email links
    EMAIL_REDIRECT_TO   testing: send EVERY email to this one address instead of the real person

Addresses on reserved test domains (example.com, *.example, *.test, ...) are never sent to,
unless EMAIL_REDIRECT_TO is set.
"""
import datetime as dt
import html
import json
import os
import re
import threading
import time
import traceback
import urllib.error
import urllib.request

from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS email_outbox (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    notification_id INTEGER REFERENCES notifications(id),
    kind TEXT NOT NULL,
    to_email TEXT NOT NULL,
    to_name TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL,
    html TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed', 'skipped', 'saved')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS login_links (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    purpose TEXT NOT NULL CHECK (purpose IN ('invite', 'reset')),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON email_outbox (status, id);
CREATE INDEX IF NOT EXISTS idx_links_user ON login_links (user_id, purpose);
"""

MAX_ATTEMPTS = 4
RESEND_URL = "https://api.resend.com/emails"
TEST_DOMAINS = re.compile(r"(^|\.)(example|test|invalid|localhost)$|^example\.(com|net|org)$", re.I)

# Notification kinds that are not emailed: the invite email already welcomes new tutors.
NOT_EMAILED = {"welcome"}

SUBJECTS = {
    "month_end": "Reminder: please submit this month's tutoring hours",
    "overdue": "Your tutoring hours are overdue",
    "manual": "Reminder from LVAEP: please submit your hours",
    "weekly": "Quick reminder: log this week's tutoring",
    "returned": "LVAEP staff asked for a change to your report",
    "assigned": "You've been assigned a student",
    "leaving": "A tutor reported that a student has stopped",
    "calendar": "Tutoring schedule update",
}

paused = False  # set while loading demo data, so seeding doesn't queue emails
_wake = threading.Event()
_worker = None


# ---------- configuration ----------

def mode():
    forced = os.environ.get("EMAIL_MODE", "").strip().lower()
    if forced in ("off", "outbox", "resend"):
        return forced
    return "resend" if os.environ.get("RESEND_API_KEY", "").strip() else "outbox"


def app_url():
    return os.environ.get("APP_URL", "http://localhost:8070").rstrip("/")


def sender():
    return os.environ.get("EMAIL_FROM", "LVAEP Tutor Hours <onboarding@resend.dev>")


def redirect_to():
    return os.environ.get("EMAIL_REDIRECT_TO", "").strip()


def outbox_dir():
    return os.environ.get("LVAEP_OUTBOX") or os.path.join(os.path.dirname(db.DB_PATH), "outbox")


def status():
    """What staff see on the Reminders page."""
    m = mode()
    return {"mode": m, "from": sender(), "app_url": app_url(), "redirect_to": redirect_to(),
            "outbox_dir": outbox_dir() if m == "outbox" else None}


def init(conn):
    conn.executescript(SCHEMA)
    conn.commit()


# ---------- templates ----------

def render(title, paragraphs, button_text=None, button_url=None, footer=None):
    """A simple, mobile-friendly email in LVAEP's colors. Returns (html, text)."""
    footer = footer or ("You're getting this because you have an LVAEP Tutor Hours account. "
                        "Questions? Reply to this email or contact LVAEP staff.")
    paras = "".join(f'<p style="margin:0 0 14px">{html.escape(p)}</p>' for p in paragraphs)
    button = ""
    if button_url:
        button = (f'<p style="margin:22px 0"><a href="{html.escape(button_url)}" style="background:#1f3a5f;color:#ffffff;'
                  f'padding:13px 22px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block">'
                  f'{html.escape(button_text or "Open LVAEP Tutor Hours")}</a></p>'
                  f'<p style="margin:0 0 14px;font-size:13px;color:#6b7280">Or copy this link: '
                  f'<span style="word-break:break-all">{html.escape(button_url)}</span></p>')
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title></head><body style="margin:0;background:#f4f6f9">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.5;color:#1f2937">
<div style="background:#1f3a5f;color:#ffffff;padding:14px 20px;border-radius:10px 10px 0 0;font-weight:bold">LVAEP Tutor Hours
<div style="font-weight:normal;font-size:12px;opacity:.85">Literacy Volunteers of America · Essex &amp; Passaic</div></div>
<div style="background:#ffffff;padding:22px 20px;border-radius:0 0 10px 10px;border:1px solid #e5e7eb;border-top:0">
<h1 style="font-size:20px;margin:0 0 14px">{html.escape(title)}</h1>{paras}{button}</div>
<p style="font-size:12px;color:#6b7280;margin:14px 4px">{html.escape(footer)}</p></div></body></html>"""
    text = "\n\n".join([title, *paragraphs] + ([f"{button_text or 'Open LVAEP Tutor Hours'}: {button_url}"] if button_url else [])
                       + ["--", footer])
    return body, text


# ---------- queueing ----------

def queue(conn, *, kind, to_email, to_name, subject, html_body, text_body, user_id=None, notification_id=None):
    conn.execute(
        """INSERT INTO email_outbox (user_id, notification_id, kind, to_email, to_name, subject, html, text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, notification_id, kind, to_email, to_name or "", subject, html_body, text_body),
    )
    _wake.set()


def queue_notification(conn, notification_id, user_id, kind, message, link=""):
    """Called by db.notify(): email the notification too, unless turned off."""
    if paused or mode() == "off" or kind in NOT_EMAILED or db.setting(conn, "email_notifications") != "1":
        return
    u = conn.execute("SELECT name, email, active FROM users WHERE id = ?", (user_id,)).fetchone()
    if not u or not u["active"]:
        return
    first = (u["name"] or "").split(" ")[0] or "there"
    url = f"{app_url()}/{link}" if link else app_url()
    body, text = render(SUBJECTS.get(kind, "Update from LVAEP Tutor Hours"), [f"Hi {first},", message],
                        "Open LVAEP Tutor Hours", url)
    queue(conn, kind=kind, to_email=u["email"], to_name=u["name"], subject=SUBJECTS.get(kind, "Update from LVAEP Tutor Hours"),
          html_body=body, text_body=text, user_id=user_id, notification_id=notification_id)
    conn.execute("UPDATE notifications SET email_status = 'queued' WHERE id = ?", (notification_id,))


# ---------- delivery ----------

def _send_resend(to_email, to_name, subject, html_body, text_body):
    payload = {"from": sender(), "to": [f"{to_name} <{to_email}>" if to_name else to_email],
               "subject": subject, "html": html_body, "text": text_body}
    if os.environ.get("EMAIL_REPLY_TO"):
        payload["reply_to"] = os.environ["EMAIL_REPLY_TO"]
    req = urllib.request.Request(RESEND_URL, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}",
        "Content-Type": "application/json", "User-Agent": "lvaep-tutor-portal/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return json.loads(res.read() or b"{}").get("id", "")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except ValueError:
            pass
        raise RuntimeError(f"Resend {e.code}: {detail}") from None


def _save_file(row):
    os.makedirs(outbox_dir(), exist_ok=True)
    safe = re.sub(r"[^\w.@-]+", "_", row["to_email"])
    path = os.path.join(outbox_dir(), f"{row['id']:05d}-{row['kind']}-{safe}.html")
    banner = (f'<div style="font-family:monospace;font-size:12px;background:#fff7d6;padding:8px 12px">'
              f'To: {html.escape(row["to_name"])} &lt;{html.escape(row["to_email"])}&gt; · '
              f'Subject: {html.escape(row["subject"])} · not sent (no RESEND_API_KEY)</div>')
    page = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + banner, row["html"], count=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page if page != row["html"] else banner + row["html"])
    return path


def deliver_pending(conn=None, limit=50):
    """Send (or save) queued emails. Safe to call any time; returns how many were handled."""
    own = conn is None
    conn = conn or db.connect()
    handled = 0
    try:
        rows = conn.execute(
            """SELECT * FROM email_outbox WHERE status = 'queued' OR (status = 'failed' AND attempts < ?)
               ORDER BY id LIMIT ?""", (MAX_ATTEMPTS, limit)).fetchall()
        m = mode()
        for row in rows:
            to_email, to_name, subject, body = row["to_email"], row["to_name"], row["subject"], row["html"]
            redirect = redirect_to()
            domain = to_email.rsplit("@", 1)[-1]
            status, error, provider_id = "sent", "", ""
            try:
                if m == "off":
                    status, error = "skipped", "Email is turned off (EMAIL_MODE=off)."
                elif m == "outbox":
                    status, provider_id = "saved", _save_file(row)
                elif redirect:
                    note = (f'<div style="font-family:Arial;font-size:13px;background:#fff7d6;padding:8px 12px">'
                            f'Test mode: this email was for {html.escape(to_name)} &lt;{html.escape(to_email)}&gt;.</div>')
                    provider_id = _send_resend(redirect, "", f"[for {to_email}] {subject}", note + body,
                                               f"(Test mode: this email was for {to_email})\n\n{row['text']}")
                elif TEST_DOMAINS.search(domain):
                    status, error = "skipped", "Test address — not sent."
                else:
                    provider_id = _send_resend(to_email, to_name, subject, body, row["text"])
            except Exception as e:  # network or provider error: retry later
                status, error = "failed", str(e)[:500]
            conn.execute(
                """UPDATE email_outbox SET status = ?, attempts = attempts + 1, last_error = ?, provider_id = ?,
                   sent_at = CASE WHEN ? IN ('sent', 'saved') THEN ? ELSE sent_at END WHERE id = ?""",
                (status, error, provider_id, status, db.now_iso(), row["id"]))
            if row["notification_id"]:
                conn.execute("UPDATE notifications SET email_status = ? WHERE id = ?", (status, row["notification_id"]))
            conn.commit()
            handled += 1
    finally:
        if own:
            conn.close()
    return handled


def wake():
    _wake.set()


def _loop():
    while True:
        _wake.wait(timeout=60)
        _wake.clear()
        time.sleep(1.5)  # let the request that queued the email finish committing
        try:
            deliver_pending()
        except Exception:
            traceback.print_exc()


def start_worker():
    global _worker
    if _worker is None:
        _worker = threading.Thread(target=_loop, name="mailer", daemon=True)
        _worker.start()
        _wake.set()


def recent(conn, limit=50):
    return [{k: r[k] for k in ("id", "kind", "to_email", "to_name", "subject", "status", "attempts", "last_error",
                               "created_at", "sent_at")}
            for r in conn.execute("SELECT * FROM email_outbox ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def expires_in(hours):
    return (dt.datetime.now() + dt.timedelta(hours=hours)).replace(microsecond=0).isoformat(sep=" ")
