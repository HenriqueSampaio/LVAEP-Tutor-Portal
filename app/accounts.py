"""Invitations and password links by email.

- Staff create an account  -> the person gets an "Accept your invitation" email (valid 7 days).
- "Forgot your password?"  -> a reset link by email (valid 24 hours).
- Staff can also email someone a fresh link from the account dialog.

Links are single-use. Only a SHA-256 hash of each token is stored, so a database leak doesn't
leak working links. The old temporary-password flow still works as a fallback.
"""
import datetime as dt
import hashlib
import secrets

from . import db, mailer
from .server import TOKEN_DAYS, ApiError, need, route, user_public

INVITE_HOURS = 7 * 24
RESET_HOURS = 24
MAX_LINKS_PER_HOUR = 3


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_link(conn, user_id, purpose, created_by=None):
    """Make a new single-use link (older unused links of the same kind stop working)."""
    now = db.now_iso()
    conn.execute("UPDATE login_links SET used_at = ? WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
                 (now, user_id, purpose))
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO login_links (user_id, purpose, token_hash, expires_at, created_by) VALUES (?, ?, ?, ?, ?)",
        (user_id, purpose, _hash(token), mailer.expires_in(INVITE_HOURS if purpose == "invite" else RESET_HOURS),
         created_by))
    return token


def send_link(conn, user, purpose, created_by=None):
    """Email an invitation or a password-reset link to `user` (a users row)."""
    token = create_link(conn, user["id"], purpose, created_by)
    url = f"{mailer.app_url()}/#/set-password?token={token}"
    first = (user["name"] or "").split(" ")[0] or "there"
    if purpose == "invite":
        role = "staff member" if user["role"] == "staff" else "volunteer tutor"
        subject = "You're invited to LVAEP Tutor Hours"
        html_body, text = mailer.render(
            "Welcome to LVAEP Tutor Hours",
            [f"Hi {first},",
             f"LVAEP has set up an account for you as a {role}. You'll use it to log your tutoring sessions "
             "and send in your monthly hours — no more paper forms.",
             "Click the button to choose your password. The link works once and expires in 7 days."],
            "Accept invitation", url)
    else:
        subject = "Reset your LVAEP Tutor Hours password"
        html_body, text = mailer.render(
            "Reset your password",
            [f"Hi {first},", "Someone (hopefully you) asked to reset your LVAEP Tutor Hours password.",
             "Click the button to choose a new one. The link works once and expires in 24 hours. "
             "If you didn't ask for this, you can ignore this email — your password won't change."],
            "Choose a new password", url)
    mailer.queue(conn, kind=purpose, to_email=user["email"], to_name=user["name"], subject=subject,
                 html_body=html_body, text_body=text, user_id=user["id"])
    return token


def _find_link(conn, token):
    row = conn.execute(
        """SELECT l.*, u.name, u.email, u.role, u.active FROM login_links l JOIN users u ON u.id = l.user_id
           WHERE l.token_hash = ?""", (_hash(token or ""),)).fetchone()
    if not row or row["used_at"] or row["expires_at"] < db.now_iso() or not row["active"]:
        raise ApiError(400, "This link has expired or was already used. Ask for a new one below.", expired=True)
    return row


def _recent_links(conn, user_id):
    since = (dt.datetime.now() - dt.timedelta(hours=1)).replace(microsecond=0).isoformat(sep=" ")
    return conn.execute("SELECT COUNT(*) AS c FROM login_links WHERE user_id = ? AND created_at > ?",
                        (user_id, since)).fetchone()["c"]


# ---------- routes ----------

@route("POST", "/api/password/forgot", auth=False)
def forgot_password(ctx):
    need(ctx.body, "email")
    u = ctx.conn.execute("SELECT * FROM users WHERE email = ?", (ctx.body["email"].strip(),)).fetchone()
    # Same answer whether or not the account exists, so the form can't be used to find out who has one.
    if u and u["active"] and _recent_links(ctx.conn, u["id"]) < MAX_LINKS_PER_HOUR:
        send_link(ctx.conn, u, "invite" if u["must_change_password"] else "reset")
        db.audit(ctx.conn, None, "account.reset_link", f"#{u['id']} (requested from sign-in page)")
    return {"ok": True}


@route("GET", "/api/password/link", auth=False)
def link_info(ctx):
    row = _find_link(ctx.conn, ctx.q("token"))
    return {"name": row["name"], "email": row["email"], "purpose": row["purpose"]}


@route("POST", "/api/password/link", auth=False)
def use_link(ctx):
    need(ctx.body, "token", "password")
    row = _find_link(ctx.conn, ctx.body["token"])
    if len(ctx.body["password"]) < 8:
        raise ApiError(400, "Choose a password with at least 8 characters.")
    ctx.conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                     (db.hash_password(ctx.body["password"]), row["user_id"]))
    ctx.conn.execute("UPDATE login_links SET used_at = ? WHERE id = ?", (db.now_iso(), row["id"]))
    ctx.conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (row["user_id"],))  # sign out other devices
    db.audit(ctx.conn, row["user_id"], "account.password_set", f"via {row['purpose']} link")
    # Sign them straight in.
    token = secrets.token_urlsafe(32)
    expires = (dt.datetime.now() + dt.timedelta(days=TOKEN_DAYS)).isoformat()
    ctx.conn.execute("INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (token, row["user_id"], expires))
    ctx.set_cookie = token
    u = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
    return {"user": user_public(u)}


@route("POST", r"/api/staff/tutors/(?P<id>\d+)/send-link", role="staff")
def staff_send_link(ctx):
    u = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (int(ctx.params["id"]),)).fetchone()
    if not u:
        raise ApiError(404, "Account not found.")
    if not u["active"]:
        raise ApiError(400, "This account is deactivated. Reactivate it first.")
    purpose = "invite" if u["must_change_password"] else "reset"
    send_link(ctx.conn, u, purpose, ctx.user["id"])
    db.audit(ctx.conn, ctx.user["id"], f"account.{purpose}_link", f"#{u['id']} {u['name']} <{u['email']}>")
    return {"ok": True, "purpose": purpose, "email": mailer.status()}


@route("GET", "/api/staff/emails", role="staff")
def staff_emails(ctx):
    return {"status": mailer.status(), "items": mailer.recent(ctx.conn)}
