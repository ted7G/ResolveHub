# ResolveHub

A support ticket tracker built on the Django admin (option 3 of the brief):
customers raise tickets, agents work them through a status workflow with
response deadlines, and the conversation lives on the ticket.

**Live:** https://cwrvuzqwcnbwqgtjbtsznccj.162.35.122.130.sslip.io/admin/

| Login | Role | What to try |
|---|---|---|
| `admin` | Support admin | Reassign tickets, bulk actions, manage agents and staff |
| `agent` | Agent | Work your own and unassigned tickets; colleagues' open read-only |
| `viewer` | Viewer | Everything read-only, internal notes hidden |

Password for all three: `12345678`, kept simple for the demo. The seed sets
it directly; passwords set in the admin must be 10+ characters. Five wrong
passwords lock a login for 15 minutes from that address. "Help with this
form" on add/edit pages is the AI helper. GitHub sign-in works after you
link GitHub from "GitHub sign-in" in the header.

## Stack and why

| | Choice | Why |
|---|---|---|
| Framework, admin | Django 5.2 LTS, built-in admin | Filters, search, inlines, actions and per-object permission hooks out of the box, so the work goes into behaviour, not UI plumbing |
| Auth | Django auth + Groups, django-axes, django-allauth | Argon2, sessions and CSRF built in; groups map to roles; axes adds lockout; allauth adds GitHub sign-in |
| Database | PostgreSQL on Neon | Managed, free tier; the schema relies on check constraints and functional unique indexes |
| File storage | S3-compatible object storage via `django-storages` | Private bucket, 10-minute signed download links; the provider is configuration only |
| Hosting | Docker image on Coolify | Git-based deploys, HTTPS, no sleeping; the `Dockerfile` runs on any Docker host (`render.yaml` is an alternative) |
| AI | OpenAI API (`gpt-4o-mini`) | One small client; `OPENAI_BASE_URL` switches to any OpenAI-compatible provider |
| Tests, CI | pytest, GitHub Actions | Real Postgres, lint, migration check, `check --deploy`, and a build-and-run test of the image |

I also considered Laravel + Filament and AdminJS; Django gave the most
admin behaviour for the least custom UI.

## Architecture

```
Customer 1──* Ticket *──1 Agent 1──1 User
                │ *──* Tag
                1──* Comment *──1 User (author; empty = the customer)
                       └─ attachment (object storage)
```

- **Business logic** (`tickets/rules.py`, `Ticket.clean()`,
  `transition_to()`): a status workflow (New → Open ⇄ Waiting → Resolved →
  Closed, with reopen), an assignee required once work starts, response
  deadlines by priority (4h to 72h) with live overdue state, and automatic
  resolved/closed timestamps. The rules are plain data, so validation, the
  status dropdown, bulk actions and the AI context all read the same source.
  Database constraints back up the important ones.
- **Admin** (`tickets/admin/`): ticket list with status/priority badges,
  deadline column, filters (overdue, assigned to me, team, tags) and search
  that also matches `RH-00042`. The ticket page shows the conversation
  read-only with an inline for replies, internal notes and attachments; the
  customer page has an inline of their tickets. Bulk actions change status
  or assign, apply the same rules per ticket, report what was skipped and
  why, and write to the admin history.
- **Roles** (`accounts/roles.py`, synced by `manage.py setup_roles`):

  | | Support admin | Agent | Viewer |
  |---|---|---|---|
  | Edit tickets (closed are read-only for all) | any | own and unassigned | no |
  | Assign tickets | anyone | only themselves | no |
  | Delete tickets, customers, tags | yes | no | no |
  | See internal notes | yes | yes | no |
  | Manage staff | yes, but not superusers | no | no |

  Lower roles see a smaller admin, not error pages: no Users section, no
  add buttons or actions for viewers, and a colleague's ticket opens
  read-only with a note saying who can edit it. The same per-ticket check
  (`tickets/permissions.py`) guards direct POSTs, bulk actions and the
  customer page, and is judged on the saved ticket.
- **GitHub sign-in** (`accounts/adapters.py`, `accounts/forms.py`): only a
  second way into an existing account its owner linked while signed in.
  Unknown GitHub accounts are refused, nothing is matched by email, and
  roles stay on the Django user, so OAuth can't grant access.
- **AI helper** (`assistant/`): the prompt is built from the form the user
  actually has open (labels, help text, choices valid for this record and
  role) plus the ticket rules. Record contents are never sent; related
  dropdowns are counted, not listed. Timeouts, rate limits, bad keys and
  provider errors return a short message in the widget, and the admin
  never depends on the call. Staff only, CSRF-protected, 500-character
  questions, 6 a minute and 100 a day per user.

## Security

- Argon2 passwords; 8-hour sessions; `Secure`/`HttpOnly`/`SameSite` cookies;
  CSRF everywhere, including the AI endpoint.
- HTTPS redirect, HSTS, `X-Frame-Options: DENY`, `nosniff`. Login lockout
  reads the client IP the proxy appended, so a forged `X-Forwarded-For`
  can't dodge it.
- Uploads: PDF, images, TXT/LOG/CSV only, 5 MB max, and the file's first
  bytes must match its extension. Stored under random names in a private
  bucket and removed when their message or ticket is deleted.
- Secrets only from environment variables; settings refuse to start in
  production without a database, storage credentials or a secret key, and
  local-disk storage is rejected unless `DEBUG` is on. The container runs
  as a normal user, and database calls time out (10s connect, 30s query).

## Running it locally

Needs Python 3.12 and PostgreSQL.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # set SECRET_KEY and DATABASE_URL
python manage.py migrate
python manage.py createcachetable
python manage.py seed              # prints the demo password unless --password is given
python manage.py runserver
pytest                             # about 175 tests
```

`seed` creates 400 customers, 3,000 tickets over six months, about 12,700
messages and 30 attachments, with a status mix that follows ticket age.
`seed --reset` replaces the help desk data and demo staff but keeps real
accounts; it stops before changing anything if a real account already uses
a demo login name.

## Deploying

The `Dockerfile` builds the image and collects static files; on start,
`docker-entrypoint.sh` runs migrations and `setup_roles`, then gunicorn
(threaded workers). `/healthz` checks the database and is the container's
health check. On Coolify: New resource → Public repository → this repo,
build pack Dockerfile, port 8000, then set:

| Variable | Value |
|---|---|
| `SECRET_KEY`, `ALLOWED_HOSTS` | random string; the app's domain |
| `DATABASE_URL` | Neon connection string (direct, not `-pooler`) |
| `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | from the storage provider |
| `S3_REGION`, `S3_ADDRESSING_STYLE` | only if the provider needs them |
| `OPENAI_API_KEY` | optional |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | optional; callback `https://<host>/accounts/github/login/callback/` |

Demo data is loaded by running `seed` once from a machine with the
production variables set. `.env.example` lists every setting.

## Trade-offs

- **Database region.** Neon runs in US West and the server elsewhere, so
  each query pays the distance and list pages take a second or two. Pages
  keep a fixed query count (tests check it), so it doesn't grow with rows;
  the real fix is a Neon project in the server's region.
- **One-file attachments.** One file per message keeps forms and validation
  simple.

## Deliberately left out

- A customer portal or public API: the brief centres on the admin, and
  customer messages already exist in the data model.
- Email in and out: it needs a mail provider and many edge cases (threading,
  bounces) for little value here.
- Pausing the deadline while waiting on the customer: it needs a status
  history to compute paused time.

## With more time

- A `TicketEvent` table: audit trail, deadline pausing and first-response
  reporting.
- Paginate the customer page's ticket inline (fine at about 35 tickets per
  customer, but it loads all of them).
- 2FA for staff, and streaming AI answers.
