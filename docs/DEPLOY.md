# Deploying the site (Vercel + Supabase)

How the live site is built, how it was set up, and how to operate it. The client-facing guide
(what the site does and how to use it) is built from `docs/build_guide_pdf.py`.

**Live site:** https://lvaep-tutor-portal-umber.vercel.app (Vercel project `lvaep-tutor-portal`).

## How it fits together

| Piece | Where | Notes |
|---|---|---|
| Web app (`public/`) | Vercel CDN | Served as static files at `/`, `/app.js`, `/styles.css`, … with the security headers from `vercel.json`. |
| API (`index.py` → `app/wsgi.py` → `app/server.py`) | One Vercel Python function (Fluid compute, region `pdx1` = AWS us-west-2, next to the database) | Every path that isn't a file in `public/` reaches it. Vercel's **Python framework preset** does this routing on its own (it's auto-detected from `requirements.txt`), so `vercel.json` has no rewrites. |
| Database | Supabase Postgres 17, project `rbsjfcwqsaommyrepxln`, AWS `us-west-2` | Reached through the **pooler** host `aws-1-us-west-2.pooler.supabase.com` — port 6543 (transaction mode) from Vercel, 5432 (session mode) from a laptop. One connection per request (automatic when `VERCEL` is set). The direct host `db.<ref>.supabase.co` is IPv6-only and is not used. |
| Daily job | Vercel Cron → `GET /api/cron/daily` | Runs the reminder rules and delivers queued email. Hobby plan: once a day, within an hour of the scheduled time (`0 13 * * *` UTC ≈ 8–10 AM Eastern). Protected by `CRON_SECRET`; safe to call twice. |
| Email | `EMAIL_MODE=stored` until Resend + LVAEP's domain are set up | Emails are kept in the database and previewable by staff (sign-in links are blanked once stored). See SETUP.md §4 to switch sending on. |

Things that differ from `python3 server.py` on a laptop, all handled in code:

- **No background threads.** When `VERCEL`/`LVAEP_SERVERLESS=1` is set, `app/server.py` delivers queued
  emails at the end of the request that queued them (`INLINE_MAIL`); the cron endpoint does the scheduled work.
- **No writable disk** (only `/tmp`). SQLite is never used there; the email "outbox" becomes the `stored` mode.
- **Server clock is UTC.** `db.today()`/`db.now_iso()` use `LVAEP_TZ` (default `America/New_York`), and
  `app/pg.py` writes database default timestamps with an explicit `AT TIME ZONE`, so month boundaries and
  the last-day-of-month reminder follow New Jersey time. `tzdata` is in `requirements.txt` for that reason.
- **Session cookie is `Secure`** when the request arrived over HTTPS (`X-Forwarded-Proto`).
- **Session settings don't persist** through the transaction pooler, which is why the code never relies on
  `SET TIME ZONE`/`SET search_path` in production and uses `prepare_threshold=None`.
- **Cold starts are cheap:** schema creation is skipped when every table and index already exists, so a new
  function instance runs two small SELECTs rather than DDL that would lock tables under live requests.

## One-time setup (done for the current site on Nov 19, 2026; repeat for a new environment)

1. **Supabase project** (supabase.com → New project; save the database password). The live project is in
   West US (Oregon, `us-west-2`); `vercel.json` pins the function to the matching Vercel region `pdx1` —
   change both together if a new project is created elsewhere.
   *Connect* → copy the **Session pooler** string (`postgres.<ref>@aws-N-<region>.pooler.supabase.com:5432`)
   into `.env` as `DATABASE_URL=…` (never commit `.env`). Don't use the "direct connection" string
   (`db.<ref>.supabase.co`): it is IPv6-only, which Vercel functions can't reach. The deploy step below
   converts the session string to the transaction pooler (port 6543) for Vercel.
2. **Run the tests on Postgres — against a throwaway database, never the live project once it holds data.**
   The suite drops and recreates its tables. Safe options:
   - a second Supabase project (free) or a local Postgres, or
   - the live project **while it is still empty**, in its own schema. `LVAEP_PG_SCHEMA` makes the app work in
     that schema only (`public` is not on the search path, every destructive statement is schema-qualified,
     and every connection checks it really is in that schema). It needs a session-mode connection: the code
     refuses a port-6543 (transaction pooler) URL outright, and the `sed` below switches the port.
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2- | sed 's/:6543\//:5432\//')" \
     LVAEP_PG_SCHEMA=lvaep_test LVAEP_ALLOW_RESET=1 LVAEP_QUIET=1 \
     .venv/bin/python -m unittest discover -s tests -t .
   ```
   Afterwards remove the test schema in the Supabase SQL editor: `DROP SCHEMA lvaep_test CASCADE;`
3. **First admin login** on the live database (creates the tables too):
   ```bash
   .venv/bin/python bootstrap_admin.py --name "Full Name" --email person@example.org
   ```
   It prints a one-time temporary password; the person chooses their own at first sign-in (until they do,
   the API only lets them change the password). The script refuses to run on a database that holds the
   synthetic demo data, so demo records can't end up on the live site.
4. **Vercel project**
   ```bash
   npx vercel login
   npx vercel link --yes --project lvaep-tutor-portal      # framework auto-detects as "Python"
   grep '^DATABASE_URL=' .env | cut -d= -f2- | sed 's/:5432\//:6543\//' \
     | npx vercel env add DATABASE_URL --environment production
   openssl rand -hex 24 | npx vercel env add CRON_SECRET --environment production
   echo stored | npx vercel env add EMAIL_MODE --environment production
   npx vercel --prod --yes                                   # prints the production URL
   echo https://<the production URL> | npx vercel env add APP_URL --environment production
   npx vercel --prod --yes                                   # again, so APP_URL is in the running function
   npx vercel git connect https://github.com/HenriqueSampaio/LVAEP-Tutor-Portal.git   # push to main = deploy
   ```
   `APP_URL` is the address used inside emails and email previews; without it the code falls back to the
   Vercel-provided production URL, but set it explicitly.
5. **Smoke test** the production URL: `/` loads, `/api/meta` answers JSON, sign in with the bootstrap
   account, create a tutor, a student and an assignment, log a session, submit, print the form.

## Environment variables (Vercel → Project → Settings → Environment Variables)

| Name | Required | Value |
|---|---|---|
| `DATABASE_URL` | yes | Supabase transaction-pooler string (6543). Secret. |
| `CRON_SECRET` | yes | Random string; Vercel sends it as `Authorization: Bearer …` to the cron path. |
| `APP_URL` | yes | `https://lvaep-tutor-portal-umber.vercel.app` (used in emails and previews). |
| `EMAIL_MODE` | no | `stored` (default on Vercel). Remove when switching email on. |
| `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_REPLY_TO` | to send email | See SETUP.md §4. |
| `LVAEP_TZ` | no | Default `America/New_York`. |
| `LVAEP_PG_POOL` | no | Leave unset on Vercel (per-request connections). |

## Day to day

- **Redeploy:** push to `main` (once Git is connected) or `npx vercel --prod` from the project folder.
  Preview deployments: `npx vercel`.
- **Logs:** `npx vercel logs --deployment <deployment-url>` or the Vercel dashboard → Deployments → Functions.
- **Admin locked out:** `bootstrap_admin.py --email … --new-password` against `DATABASE_URL`.
- **Clear test records before real use:** the cleanest is a fresh Supabase project (new `DATABASE_URL`) and
  `bootstrap_admin.py`. On the same project (take a backup first — this drops every table):
  ```bash
  LVAEP_ALLOW_RESET=1 .venv/bin/python -c 'from app import env; env.load(); from app import db; db.reset()'
  .venv/bin/python bootstrap_admin.py --name "Full Name" --email person@example.org
  ```
  Avoid running `server.py` against the live database. If you do (DATABASE_URL in `.env`), it now keeps the
  scheduler and mailer threads OFF for a remote database unless you pass `--background`, so a laptop can't
  act as the live site's scheduler. Use `DATABASE_URL= python3 server.py` for a normal local run.
- **Backups:** Supabase Free has none. Export before risky changes (`pg_dump` with the session pooler URL,
  or Supabase dashboard → Database → Backups on Pro). Pro ($25/month) adds daily backups and removes the
  7-day inactivity pause. The daily cron's queries count as database activity, which should keep a Free
  project from pausing; if it pauses anyway, restore it from the Supabase dashboard (about a minute).
- **Cron didn't run?** Hobby crons fire within ±59 min of the schedule and are not retried; the endpoint is
  idempotent (a period is claimed before anyone is notified), so hitting it again is safe:
  `curl -H "Authorization: Bearer $CRON_SECRET" https://<site>/api/cron/daily`.
  Staff can also press **Run today's check now** on the Reminders page.

## Limits to know (Hobby plan, verified Nov 2026)

Function 60 s max duration (set in `vercel.json`; plan allows up to 300 s), 4.5 MB request/response body
(the print-all-forms page for ~110 students is ≈2 MB), one cron per day, personal GitHub repos only for
Git integration. Vercel's Hobby terms are for non-commercial use; move the project to a Pro team (or an
LVAEP-owned account) when the site goes into real service.
