# Deploying the site (Vercel + Supabase)

How the live site is built, how it was set up, and how to operate it. The client-facing guide
(what the site does and how to use it) is built from `docs/build_guide_pdf.py`.

## How it fits together

| Piece | Where | Notes |
|---|---|---|
| Web app (`public/`) | Vercel CDN | Served as static files at `/`, `/app.js`, `/styles.css`, … |
| API (`index.py` → `app/wsgi.py` → `app/server.py`) | One Vercel Python function (Fluid compute, region `iad1`) | Every path that isn't a file in `public/` reaches it. Vercel's **Python framework preset** does this routing on its own (it's auto-detected from `requirements.txt`), so `vercel.json` has no rewrites. |
| Database | Supabase Postgres, AWS `us-east-1` | Reached through the **transaction pooler** (port 6543). One connection per request (`LVAEP_PG_POOL=0` behaviour is automatic when `VERCEL` is set). |
| Daily job | Vercel Cron → `GET /api/cron/daily` | Runs the reminder rules and delivers queued email. Hobby plan: once a day, within an hour of the scheduled time (`0 13 * * *` UTC ≈ 8–10 AM Eastern). Protected by `CRON_SECRET`. |
| Email | `EMAIL_MODE=stored` until Resend + LVAEP's domain are set up | Emails are kept in the database and previewable by staff. See SETUP.md §4 to switch sending on. |

Things that differ from `python3 server.py` on a laptop, all handled in code:

- **No background threads.** `app/server.py` delivers queued emails at the end of the request that queued
  them when `LVAEP_SERVERLESS=1`/`VERCEL` is set (`INLINE_MAIL`), and the cron endpoint does the scheduled work.
- **No writable disk** (only `/tmp`). SQLite is never used there; the email "outbox" becomes the `stored` mode.
- **Server clock is UTC.** `db.today()`/`db.now_iso()` use `LVAEP_TZ` (default `America/New_York`), and
  `app/pg.py` writes database default timestamps with an explicit `AT TIME ZONE`, so month boundaries and
  the last-day-of-month reminder follow New Jersey time. `tzdata` is in `requirements.txt` for that reason.
- **Session cookie is `Secure`** when the request arrived over HTTPS (`X-Forwarded-Proto`).
- **Session settings don't persist** through the transaction pooler, which is why the code never relies on
  `SET TIME ZONE`/`SET search_path` in production, and uses `prepare_threshold=None`.

## One-time setup (already done for the current site; repeat for a new environment)

1. **Supabase project** (supabase.com → New project; region East US; save the database password).
   *Connect* → **Transaction pooler** string → put it in `.env` as `DATABASE_URL=…:6543/postgres`
   (percent-encode special characters in the password). Never commit `.env`.
2. **Tests against that database, in an isolated schema** (optional but recommended; the suite drops and
   recreates its tables, so it must never run against the live schema):
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   # session pooler (port 5432) for this: the schema setting is per connection
   DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2- | sed 's/:6543\//:5432\//')" \
     LVAEP_PG_SCHEMA=lvaep_test LVAEP_ALLOW_RESET=1 LVAEP_QUIET=1 \
     .venv/bin/python -m unittest discover -s tests -t .
   ```
   Afterwards drop the schema in the Supabase SQL editor: `DROP SCHEMA lvaep_test CASCADE;`
3. **First admin login** on the live database (creates the tables too):
   ```bash
   .venv/bin/python bootstrap_admin.py --name "Full Name" --email person@example.org
   ```
   It prints a one-time temporary password. The script refuses to run on a database that holds the
   synthetic demo data, so demo records can't end up on the live site.
4. **Vercel project**
   ```bash
   npx vercel login
   npx vercel link                      # new project, personal scope; framework auto-detects as "Python"
   grep '^DATABASE_URL=' .env | cut -d= -f2- | npx vercel env add DATABASE_URL --environment production
   openssl rand -hex 24 | npx vercel env add CRON_SECRET --environment production
   echo stored | npx vercel env add EMAIL_MODE --environment production
   npx vercel --prod                    # prints the production URL
   npx vercel git connect https://github.com/HenriqueSampaio/LVAEP-Tutor-Portal.git   # push to main = deploy
   ```
   Set `APP_URL` to the site's address once known (it is only used inside emails).
5. **Smoke test** the production URL: `/` loads, `/api/meta` answers JSON, sign in with the bootstrap
   account, create a tutor, a student and an assignment, log a session, submit, print the form.

## Environment variables (Vercel → Project → Settings → Environment Variables)

| Name | Required | Value |
|---|---|---|
| `DATABASE_URL` | yes | Supabase transaction-pooler string (6543). Secret. |
| `CRON_SECRET` | yes | Random string; Vercel sends it as `Authorization: Bearer …` to the cron path. |
| `EMAIL_MODE` | no | `stored` (default on Vercel). Remove when switching email on. |
| `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_REPLY_TO`, `APP_URL` | to send email | See SETUP.md §4. |
| `LVAEP_TZ` | no | Default `America/New_York`. |
| `LVAEP_PG_POOL` | no | Leave unset on Vercel (per-request connections). |

## Day to day

- **Redeploy:** push to `main` (if Git is connected) or `npx vercel --prod` from the project folder.
  Preview deployments: `npx vercel`.
- **Logs:** `npx vercel logs <deployment-url>` or the Vercel dashboard → Deployments → Functions.
- **Admin locked out:** `bootstrap_admin.py --email … --new-password` against `DATABASE_URL`.
- **Clear test records before real use:** easiest is a fresh Supabase project (new `DATABASE_URL`) +
  `bootstrap_admin.py`; or `LVAEP_ALLOW_RESET=1 .venv/bin/python server.py --reset --empty` then fix the admin
  with `bootstrap_admin.py --new-password` (this drops every table — take a backup first).
- **Backups:** Supabase Free has none. Export before risky changes (`pg_dump` with the session pooler URL,
  or Supabase dashboard → Database → Backups on Pro). Pro ($25/month) adds daily backups and removes the
  7-day inactivity pause.
- **Cron didn't run?** Hobby crons fire within ±59 min of the schedule and are not retried; the endpoint is
  idempotent, so hitting it again is safe: `curl -H "Authorization: Bearer $CRON_SECRET" https://<site>/api/cron/daily`.
  Staff can also press **Run today's check now** on the Reminders page.

## Limits to know (Hobby plan, verified Nov 2026)

Function 60 s max duration (set in `vercel.json`; plan allows up to 300 s), 4.5 MB request/response body
(the print-all-forms page for ~110 students is ≈2 MB), one cron per day, personal GitHub repos only for
Git integration. Vercel's Hobby terms are for non-commercial use; move the project to a Pro team (or an
LVAEP-owned account) when the site goes into real service.
