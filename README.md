# ResolveHub

A support ticket tracker built on the Django admin: customers raise tickets,
agents work them through a status workflow with response deadlines, and the
conversation (replies, internal notes, attachments) lives on the ticket.

Built for the take-home brief using option 3, the support ticket tracker.

## Stack and why

| Concern | Choice | Reason |
|---|---|---|
| Framework and admin | Django 5.2 LTS + the built-in admin | The brief rewards customising a generated admin. Django's has list filters, search, inlines, actions, and per-object permission hooks out of the box, so the work goes into behaviour rather than UI plumbing. LTS until April 2028. |
| Auth and roles | Django auth + Groups, django-axes, django-allauth | Proper password hashing (Argon2 first), sessions and CSRF come built in. Groups map cleanly to roles, and object-level rules hook into `ModelAdmin.has_change_permission`. Axes adds login lockout; allauth adds optional GitHub sign-in. |
| Database | PostgreSQL on Neon | Managed Postgres with a usable free tier. Check constraints and functional unique indexes are used, so SQLite was never an option, not even locally. |
| File storage | MinIO via `django-storages` | S3-compatible object storage running next to the app on the same Coolify server: a private bucket, signed download links. Cloudflare R2, Backblaze B2 or AWS S3 are a configuration change, no code. |
| Hosting | Docker image on Coolify (self-hosted VPS) | Git-based deploys with HTTPS from Let's Encrypt, and no sleeping between visits. The `Dockerfile` runs on any Docker host; a Render blueprint is kept as a managed alternative. |
| Static files | WhiteNoise | Serves hashed, compressed static files from the app itself; no CDN or extra bucket needed at this size. |
| AI assistant | OpenAI API (any OpenAI-compatible endpoint) | One small client. `OPENAI_BASE_URL` points it at Groq, Gemini or a self-hosted model without code changes. |
| Tests and CI | pytest + pytest-django, GitHub Actions | Tests run against real Postgres in CI, plus lint, a migration check and Django's deploy checklist. |

I considered Laravel + Filament (excellent admin, but more of the admin
would be bespoke components) and a JS stack with AdminJS (weaker inlines
and permissions). Django gives the most out of the box for this brief.

## What's in it

**Data model** (`tickets/models.py`)

```
Customer 1──* Ticket *──1 Agent 1──1 User
                │  *
                │  └──* Tag            (many-to-many)
                1
                └──* Comment *──1 User (author; empty = the customer)
                       └─ attachment   (file in object storage)
```

Constraints live in the database as well as in forms: valid status and
priority values, case-insensitive unique customer emails and tag names,
"resolved tickets have a resolution time", and "customer messages can't be
internal notes".

**Business logic** (`tickets/rules.py`, `Ticket.clean()`, `Ticket.transition_to()`)

- Status workflow: New → Open / Resolved / Closed, Open ⇄ Waiting on customer,
  Open / Waiting → Resolved, Resolved → Open (reopen) / Closed. Closed is final.
- Open, Waiting on customer and Resolved need an assignee; unavailable agents
  can't receive new tickets.
- Response deadline by priority (urgent 4h, high 8h, normal 24h, low 72h),
  recalculated when priority changes; tickets past it are overdue while active.
- Resolution and closing timestamps are maintained automatically.

The rules are plain data in `rules.py`, so the model validation, the admin's
status dropdown, the bulk actions and the AI assistant's context all read
the same definitions.

**Admin customisation** (`tickets/admin/`)

- Ticket list: coloured status and priority, live "Overdue by 3 hours" /
  "Due in 5 hours" column, comment count, filters for deadline, assignment
  ("Assigned to me"), team, agent, tags and date. Search covers subject,
  customer name, email and company, and also ticket numbers like `RH-00042`.
- Ticket page: the conversation is shown read-only (what was said to a
  customer shouldn't be rewritten), with a separate inline for adding a
  reply, internal note or attachment. The author is set from the login.
  The status dropdown only offers moves that are valid from the current status.
- Customer page: inline list of that customer's tickets with editable
  status, priority and assignee, still validated by the workflow.
- Bulk actions: move to Open / Waiting / Resolved / Closed, assign to me,
  assign to a chosen agent (agent picker next to the action menu). Each
  ticket goes through the same model rules; skipped tickets are reported
  with the reason ("12 tickets moved to Resolved. 3 skipped: Assign an agent
  before..."), and every change is written to the admin history.
- Agents list with active and overdue counts, and an inline availability toggle.

**Roles** (`accounts/roles.py`, synced by `manage.py setup_roles`)

| | Support admin | Agent | Viewer |
|---|---|---|---|
| See tickets, customers, agents, tags | yes | yes | yes |
| Edit tickets | any | own and unassigned | no |
| Bulk status actions / assign to me | yes | own and unassigned only | no |
| Assign to another agent in bulk | yes | no | no |
| Add / edit customers, add tags | yes | yes | no |
| Delete anything | yes | no | no |
| See internal notes | yes | yes | no |
| Manage staff accounts and roles | yes | no | no |

A lower role sees a visibly smaller admin rather than error pages: no Users
section, no add buttons or bulk actions for viewers, and a colleague's ticket
opens read-only with a note explaining who can edit it. The same check
refuses direct POSTs and is applied per ticket in bulk actions. Support
admins can manage staff, but can't grant superuser status or raw
permissions, or edit a superuser's account.

**Sign in with GitHub** (optional, `accounts/adapters.py`)

Enabled when `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are set. GitHub
is a second way into an existing staff account, never a way to get one:

- a staff member signs in with their password once and links GitHub from
  the "GitHub sign-in" link in the admin header;
- after that, "Sign in with GitHub" on the login page works for them;
- an unknown GitHub account is refused, and no user is created;
- accounts are not matched by email. A GitHub account showing the same
  address as a staff member gets nothing until that staff member links it.
  (allauth's email matching would also wipe the local password of any
  account whose email it hasn't verified itself, which is every account
  created in the admin.)

Roles stay on the Django user, so OAuth can't grant or change access.

**AI form assistant** (`assistant/`)

A "Help with this form" panel on every add/change page. The prompt is built
from the form the user actually has open (`assistant/context.py`):

- the ModelAdmin's form for that user and record: labels, help text,
  required flags, max lengths, and choices (status options are the ones
  valid from the current status);
- the inline "Add a reply" fields;
- the ticket rules, generated from `tickets/rules.py`.

It never includes record content (subjects, descriptions, names, emails);
related-record dropdowns are counted, not listed. The system prompt tells
the model to answer only from that reference and to treat the question as
data, not instructions.

Failure handling: no API key, timeouts (20s), provider rate limits, bad
keys and empty answers each return a short message the widget shows in
place of an answer. The admin page itself never depends on the call.
Requests need a staff login and a CSRF token, questions are capped at 500
characters, the body at 4 KB, and each user is limited to 6 questions a
minute and 100 a day (database cache, so the limits hold across workers).

## Security notes

- Passwords: Argon2 (`PASSWORD_HASHERS`), minimum length 10 plus Django's validators.
- Brute force: five failed logins for the same username from the same IP
  lock that pair out for 15 minutes (django-axes). The client IP is the
  entry the platform's proxy appends to `X-Forwarded-For`; entries to its
  left are ignored because the client can forge them.
- Sessions: 8-hour lifetime; session and CSRF cookies are `Secure`, `HttpOnly`, `SameSite=Lax` in production.
- HTTPS: `SECURE_SSL_REDIRECT`, HSTS (30 days), scheme taken from the proxy's `X-Forwarded-Proto`; `X-Frame-Options: DENY`, `nosniff`.
- CSRF on all state-changing requests, including the assistant endpoint.
- Uploads: allowed types only (PDF, PNG, JPG, GIF, TXT, LOG, CSV), 5 MB max,
  and the first bytes must match the extension, so a renamed executable or
  an HTML page is rejected. Stored under random keys in a private bucket and
  served through 10-minute signed URLs. Nothing is executed or rendered as HTML.
- Secrets only come from environment variables. Settings refuse to start
  without `SECRET_KEY`, a PostgreSQL `DATABASE_URL`, or object storage
  credentials in production; the local-disk storage option is rejected
  unless `DEBUG` is on.
- The container runs as an unprivileged user, and secrets are kept out of the image (`.dockerignore`).
- CI runs `manage.py check --deploy` against production settings, then builds
  the image and checks it starts, reports healthy and serves pages through the proxy.

## Running it locally

Requirements: Python 3.12 and a PostgreSQL database (local, Docker, or a
free Neon branch).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # then set SECRET_KEY and DATABASE_URL

python manage.py migrate
python manage.py createcachetable
python manage.py seed              # prints the demo password unless you pass --password
python manage.py runserver
```

Open http://localhost:8000/admin/ and sign in as `demo-admin`, `demo-agent`
or `demo-viewer` to see the three roles.

With `STORAGE_BACKEND=local` (allowed only with `DEBUG=True`) uploads go to
`./media`; set the `S3_*` variables to use MinIO, R2 or S3 instead.

### Seed data

```bash
python manage.py seed --reset                     # replace everything
python manage.py seed --reset --tickets 10000     # more volume
python manage.py seed --reset --password 'your-demo-password'
```

Defaults: 400 customers, 3,000 tickets over 180 days, about 12,000
messages, 30 attachments, 17 staff (3 demo logins plus 14 colleagues who
can't log in). The status mix depends on ticket age and all timestamps
follow the workflow, so filters such as "Overdue" return realistic results.
`--reset` deletes help desk data and seeded staff only; real accounts are kept.
`--seed N` makes runs repeatable.

### Tests

```bash
pytest
```

About 150 tests cover the workflow and SLA rules, attachment validation,
each role's view of the admin (through real requests, including forged
POSTs), bulk actions, login lockout, the GitHub sign-in flow (through the
real allauth views with GitHub's responses faked), the seed command, the
assistant's context building and every provider failure mode, plus a
query-count guard on the ticket list.

## Deploying (Neon + Coolify + MinIO)

Production runs the `Dockerfile` on a Coolify server, with the database on
Neon and uploads in MinIO on the same server.

1. **Neon**: create a project and copy the direct connection string
   (`postgresql://...?sslmode=require`, without `-pooler` in the host).
2. **MinIO**: add it in Coolify (New resource → Service → MinIO) and give its
   API a public HTTPS domain, for example `files.example.com`. Signed
   download links point there, so browsers must be able to reach it. In the
   MinIO console create a private bucket and an access key limited to it.
3. **The app**: New resource → Public repository → this repository, build
   pack **Dockerfile**, port **8000**, and a domain. Set the variables below
   and deploy.

| Variable | Value |
|---|---|
| `SECRET_KEY` | a long random string |
| `ALLOWED_HOSTS` | the app's domain, e.g. `resolvehub.example.com` (the matching HTTPS origin is trusted for forms automatically) |
| `DATABASE_URL` | Neon connection string |
| `S3_ENDPOINT_URL` | MinIO's public API address, e.g. `https://files.example.com` |
| `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | from MinIO |
| `S3_REGION`, `S3_ADDRESSING_STYLE` | `us-east-1` and `path` for MinIO |
| `OPENAI_API_KEY` | optional; the assistant explains it's not set up without it |
| `OPENAI_MODEL`, `OPENAI_BASE_URL` | optional; default `gpt-4o-mini` on OpenAI |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | optional, from a GitHub OAuth app with callback `https://<host>/accounts/github/login/callback/` |
| `TRUSTED_PROXY_COUNT` | `1` (Coolify's proxy); `2` if the domain is also proxied by a CDN |

`DEBUG` defaults to off. Static files are collected while the image is
built. Each time the container starts it runs `migrate`, `createcachetable`
and `setup_roles` (`docker-entrypoint.sh`), then gunicorn
(`gunicorn.conf.py`; `WEB_CONCURRENCY` sets the worker count). To load demo
data, run the seed command once from your machine with `DATABASE_URL` and
the `S3_*` variables pointing at production.

`/healthz` checks the database and is the container's Docker health check.
It is answered before the host and HTTPS checks, because the probe calls
the container on its internal address; every other path still enforces
both. Logs go to stdout, so a 500 shows up with its traceback in Coolify's
log view.

**Render instead of Coolify.** `render.yaml` describes the same service for
Render (New → Blueprint → this repository). It runs `build.sh` instead of
the Docker image and trusts Render's hostname automatically. Cloudflare R2
works as the storage there: use the account's S3 endpoint
(`https://<account-id>.r2.cloudflarestorage.com`) and leave the region and
addressing style unset.

## Deliberately left out

- **A customer-facing portal or public API.** The brief centres on the
  admin; customer messages exist in the data model (comments without an
  author) and are created by the seed command.
- **Email notifications and inbound email.** They're how a real help desk
  receives tickets, but they need a mail provider and a lot of edge cases
  (threading, bounces) for little value here.
- **Pausing the SLA clock while waiting on the customer.** Real help desks
  do this. It needs a history of status changes to compute paused time,
  which is a model of its own.
- **Multiple attachments per comment.** One file per comment keeps the form
  and validation simple; a separate Attachment model is the obvious next step.

## What I'd do with more time

- Record status changes in a `TicketEvent` table: an audit trail, SLA pause
  on "Waiting on customer", and first-response-time reporting.
- Paginate the customer page's ticket inline. It's fine at seed volumes (the
  busiest customer has about 35 tickets), but it loads all of them.
- Move counts on the list pages to cached or denormalised columns if tickets
  grew past a few hundred thousand. The list already avoids the full row
  count and runs a constant 12 queries.
- Optional 2FA for staff (allauth ships an MFA app).
- Stream assistant answers, and cache answers per form and question.

## Project layout

```
config/       settings (environment-driven), URLs, health check
Dockerfile    production image; docker-entrypoint.sh and gunicorn.conf.py start it
render.yaml   Render blueprint (alternative host), runs build.sh
accounts/     roles, setup_roles command, hardened user admin, login lockout IP, GitHub sign-in rules
tickets/      models, rules, validators, permissions, admin package, seed command
assistant/    form context builder, model client, endpoint, rate limit, widget
tests/        shared test helpers and project-level tests
```
