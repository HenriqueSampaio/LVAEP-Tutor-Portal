# Supabase, email invitations and notifications

This branch adds two things to the prototype:

1. **Supabase (Postgres) as the database**: set one setting and the app stores everything in a Supabase
   project instead of the local SQLite file. Nothing else changes: the same code, tests and SQL run on both.
2. **Email**: invitation emails for new accounts, "Forgot your password?", and email copies of
   notifications (reminders, returned reports, new students, schedule changes). Sent through
   [Resend](https://resend.com).

Everything works without any accounts. With no settings, the app uses SQLite and saves emails as
`.html` files in `data/outbox/` so you can open them. Add Supabase and Resend only when you want them.

> **Use only fake data** until LVAEP signs off on hosting and privacy. The demo data (`python3 server.py --reset`) is all synthetic.

---

## 1. Run it locally (no accounts needed)

```bash
python3 server.py --reset         # demo data, http://localhost:8070
python3 -m unittest discover -s tests -t . -v
```

Sign in as `dana@lvaep.example` / `demo1234` (staff), create an account under **Tutors & accounts**,
and open the invitation it saved in `data/outbox/`. The link in it works locally.

## 2. Settings file

Copy `.env.example` to `.env` and fill in what you need. `.env` is git-ignored, so **never commit it,
and never paste its contents into chat, issues or pull requests.** `server.py` and `check_setup.py`
read it automatically. A hosting service's own environment variables override it.

## 3. Supabase

**Make a new project for this app.** Don't reuse another app's project: table names would clash.
Using one shared project for the team's development is simplest.

1. Go to [supabase.com](https://supabase.com) → **New project**.
   - Name: `lvaep-tutor-portal-dev`.
   - Region: **East US (North Virginia)**, closest to New Jersey.
   - Set a **database password** and save it in a password manager. You'll need it in step 3.
2. Wait for the project to finish setting up (about a minute).
3. Click **Connect** at the top of the project page. Under **Session pooler**, copy the connection string.
   Replace `[YOUR-PASSWORD]` with your database password and paste it into `.env`:
   ```
   DATABASE_URL=postgresql://postgres.abcdefghijklmnop:YOUR-DB-PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres
   ```
   - **Use the Session pooler, not "Direct connection".** On the free plan the direct connection only works over IPv6, which most home and campus networks don't have.
   - **Don't use the "Transaction pooler" either.** It's meant for serverless functions.
   - If your password contains `@ # ? & /` or spaces, percent-encode them (for example `#` → `%23`).
4. Install the Postgres driver. It's only needed for Supabase; SQLite needs nothing extra.
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
5. Check the connection. This also creates the tables:
   ```bash
   .venv/bin/python check_setup.py
   ```
   Optionally, also put the project's URL and **publishable key** in `.env` (Project Settings → **API Keys**).
   The check then confirms that Supabase's public API can't read the tables.
6. Start the app on Supabase:
   ```bash
   .venv/bin/python server.py           # first run on an empty project loads the fake demo data
   .venv/bin/python server.py --empty   # …or start with just one admin account instead
   ```
   You can open **Table Editor** in the Supabase dashboard to watch the data appear.

**Starting over:** on Postgres, `--reset` deletes every table's data. Because the database is shared,
it only runs if you also set `LVAEP_ALLOW_RESET=1` for that command:
```bash
LVAEP_ALLOW_RESET=1 .venv/bin/python server.py --reset
```

### How the Supabase setup is secured
- The app has its **own** sign-in (passwords, sessions), so it doesn't use Supabase Auth. It connects to
  the database directly with the database password. Browsers never talk to Supabase.
- Supabase also publishes every table through a public web API. On startup the app turns on **row-level
  security with no policies** for every table and revokes access from Supabase's `anon` and `authenticated`
  roles, so that API can't read or change anything. `check_setup.py` verifies this.
- Keep `DATABASE_URL` secret: it's the key to all the data. If it leaks, reset the database password in
  Project Settings → Database.

## 4. Email (Resend)

### Testing with fake data (no domain needed)
1. Sign up at [resend.com](https://resend.com). Use the email address you want the test emails to arrive at.
2. Go to **API Keys** → **Create API Key**, with permission **Sending access**. Copy it into `.env`:
   ```
   RESEND_API_KEY=re_...
   EMAIL_FROM=LVAEP Tutor Hours <onboarding@resend.dev>
   EMAIL_REDIRECT_TO=the-email-you-signed-up-with@gmail.com
   ```
   Until a domain is verified, Resend only delivers to your own account's address. `EMAIL_REDIRECT_TO`
   sends **every** email the app sends to you instead of the (fake) tutor. Each email says at the top who
   it was meant for, so you can test invites and reminders for any demo tutor.
3. Send yourself a test:
   ```bash
   .venv/bin/python check_setup.py --send-test the-email-you-signed-up-with@gmail.com
   ```
4. Start the app, create an account (or press **Send a reminder now** on the Reminders page), and check
   your inbox. The **Recent emails** list on the Reminders page shows every email and whether it was sent.

### For real use (LVAEP's domain)
Someone with access to LVAEP's domain settings has to do this:
1. In Resend: **Domains** → **Add domain**. Use a subdomain such as `mail.lvaep.org`.
2. Add the DNS records Resend shows (SPF and DKIM; adding DMARC is recommended) wherever LVAEP's domain is managed.
   Verification usually takes minutes, but can take up to a couple of days.
3. In `.env` or the hosting settings:
   ```
   EMAIL_FROM=LVAEP Tutor Hours <hours@mail.lvaep.org>
   EMAIL_REPLY_TO=<LVAEP's office email>
   APP_URL=https://<the site's address>
   ```
   Then remove `EMAIL_REDIRECT_TO`.

### What gets emailed

| Email | When | Can staff turn it off? |
|---|---|---|
| **Invitation** ("Accept invitation", valid 7 days) | Staff create an account | No |
| **Password reset** (valid 24 hours) | "Forgot your password?" on the sign-in page, or **Email sign-in link** in the account dialog | No |
| Month-end, overdue and weekly reminders; "Remind tutor" | Same rules as the in-app reminders | Yes, Reminders page → *Also send notifications by email* |
| Report returned, new student assigned, student stopped (to staff), calendar changes | When they happen | Yes, same switch |

Details:
- **Links:** single-use and expiring. Only a hashed copy is stored. A new link cancels the person's
  previous one. "Forgot password" answers the same way whether or not the email has an account, and allows 3 requests an hour.
- **Temporary passwords:** they still work as a backup. The account dialog shows one if an email doesn't arrive.
- **Reliability:** emails are queued in the same database transaction as whatever caused them, so a failed
  action never sends a stray email. Failed sends retry (up to 4 tries).
- **Test addresses:** addresses on reserved test domains (`*.example`, `example.com`, `*.test`, …), like the
  demo accounts, are never actually emailed, unless `EMAIL_REDIRECT_TO` is set.

## 5. Hosting (when the team is ready)

This app is a long-running Python server. It also runs the reminder schedule and the email sender in the
background, so it needs a host that keeps it running all the time. Serverless hosts like Vercel or Netlify
won't work.

- **Railway** (Hobby, $5/month, includes $5 of usage). A small app like this should fit in that.
  Start command: `pip install -r requirements.txt && python3 server.py --host 0.0.0.0`
  (the port comes from Railway automatically).
- **Render**: its free plan shuts the app down after 15 minutes without visitors, which would stop reminders
  and emails, so it needs a paid plan.
- On either host, set the same variables as in `.env` in the host's settings, and set `APP_URL` to the
  site's address. The host provides HTTPS.
- Put the host in the same region as the Supabase project (US East). Every page makes several database
  queries, and a distant host makes each one slower.

## 6. What it costs LVAEP

| Service | Development (now) | Real use |
|---|---|---|
| Supabase | Free plan: 500 MB, pauses after 1 week without use, **no backups** | **Pro, $25/month**: daily backups (kept 7 days), never pauses, spend cap on by default. Ask Supabase about a nonprofit rate. |
| Resend | Free: 3,000 emails/month, 100/day | Free is enough. About 50 tutors with weekly reminders is roughly 300 emails a month. Paid plans are 50% off for registered nonprofits. |
| Hosting | Run it on your laptop | About $5–7/month (see above) |
| **Total** | **$0** | **About $30–35/month**, mostly Supabase Pro (for backups) |

LVAEP is tiny for Supabase: about 50 tutors, about 110 students and a few staff. The main reason to pay
for Pro is **automatic backups** of real records.

## 7. Notes for developers

- **Keep writing SQLite-style SQL** (`?` placeholders, `INSERT OR IGNORE`, `GROUP_CONCAT`, `cur.lastrowid`).
  `app/pg.py` translates it for Postgres, and the schema in `app/db.py` is converted automatically,
  including new tables and `ALTER TABLE` additions.
- **Two rules for Postgres:**
  - Don't use `INSERT OR REPLACE`; write `INSERT ... ON CONFLICT (...) DO UPDATE` yourself.
  - Don't catch an `IntegrityError` and keep using the same connection. Postgres aborts the transaction;
    raise an `ApiError` as the existing code does.
- **Run the whole test suite on Postgres too** (needs a local Postgres or a throwaway database, never the
  shared Supabase project, because the tests wipe the tables):
  ```bash
  createdb lvaep_test
  DATABASE_URL=postgresql:///lvaep_test LVAEP_ALLOW_RESET=1 .venv/bin/python -m unittest discover -s tests -t . -v
  ```
- **New files on this branch:**
  - `app/pg.py`: Postgres support
  - `app/mailer.py`: email queue, templates and delivery
  - `app/accounts.py`: invitation and password-link routes
  - `app/env.py`: `.env` loader
  - `check_setup.py`: the setup check
