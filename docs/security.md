# Security

How Karobar ERP defends itself, and what each new piece of code has to keep true. Report
vulnerabilities as described in [SECURITY.md](../SECURITY.md).

The worst thing that can happen here is one business seeing or changing another business's books.
Everything else is ranked below that.

## Tenancy

- Every tenant-owned model extends `TenantOwnedModel`. Its default manager filters by the active
  tenant and raises `TenantNotSetError` when there is none, so a forgotten filter fails loudly
  instead of returning every tenant's rows. `all_tenants` is the explicit escape hatch; each use
  needs a comment saying why.
- `save()` refuses to write a row whose tenant is not the active one.
- `TenantMiddleware` activates a tenant from the `X-Tenant` header only if the signed-in user is a
  member. Unknown, malformed and foreign tenant ids all answer the same `404`.
- `tests/tenancy/test_isolation.py` lists every API route as public, user-level or tenant-owned.
  A new route that is not listed fails CI. Tenant-owned routes are called as a member of another
  tenant and must answer `404` (detail) or an empty list (collection).
- Clients see `public_id` (UUID) values, never sequential primary keys of users or tenants.

## Authentication and sessions

- Session cookies: `HttpOnly`, `Secure` and `SameSite=Lax`, named with the `__Host-` prefix in
  production so they can't be set by a subdomain. Sessions last 12 hours.
- CSRF: Django's middleware plus `X-CSRFToken` from the SPA. DRF skips CSRF for anonymous
  requests, so `LoginView` adds `csrf_protect` itself; sign-in CSRF is tested.
- No access or refresh tokens in `localStorage` or `sessionStorage`; ESLint blocks
  `localStorage.setItem`.
- Passwords: Argon2id first in `PASSWORD_HASHERS`, at least 12 characters, common and numeric-only
  passwords rejected. If Argon2id can't compute a hash (memory pressure is the realistic case),
  `apps/accounts/hashers.py` falls back to bcrypt, logs a warning, and the password is rehashed with
  Argon2id at the next sign-in. PBKDF2 stays only to verify and upgrade old hashes. Passwords are
  never hashed in the browser: the hash would become the password, and TLS already protects it on
  the wire.
- Sign-in answers the same message for an unknown email and a wrong password. Django runs the
  hasher for unknown users too, so timing doesn't reveal which emails exist.

### Bot checks on public forms

Sign-in, sign-up and password reset carry two checks (`apps/accounts/humans.py`):

- A honeypot field (`website`) that is positioned off screen, `aria-hidden` and out of the tab
  order. When it is filled in, sign-up and reset answer exactly as for a real request and do
  nothing, and sign-in answers with the usual wrong-password message, so a bot learns nothing.
- Google reCAPTCHA v3, verified server side at `siteverify` with the secret key. The token's
  `action` must match the form (`login`, `signup`, `password_reset`), so a token can't be
  replayed on another form. A score under `RECAPTCHA_V3_MIN_SCORE` (default 0.5), a missing
  token or a failed check answers `400` with `code: captcha_v2_required`, and the form then
  shows the v2 checkbox, whose token is verified with the v2 secret.
- If Google can't be reached the form fails closed with `503 captcha_unavailable`.
- The v3 badge is rendered inline, under the submit button of the form it protects, using
  explicit rendering and the widget id. The automatic badge can only float over a screen corner.
  The written notice is used only if a business has v2 keys and no v3 keys.
- Empty keys turn reCAPTCHA off for local development and tests; `config.settings.prod`
  refuses to start without both key pairs.

### Sign in with Google and Facebook

`apps/accounts/oauth.py` runs the OAuth 2.0 authorization code flow itself, on the standard
library (`apps/platform/http.py`: https only, 8 second timeout, 256 KB cap, JSON objects only).

- `state` is 32 random bytes kept in the session and compared in constant time; Google also
  gets PKCE (S256). The code is exchanged server to server with the client secret, and the
  provider's tokens are never stored or sent to the browser. Facebook Graph calls carry
  `appsecret_proof`.
- A provider identity is stored as (provider, provider user id) in `SocialAccount`, so a later
  change of email at the provider can't move the identity to another user.
- An identity is linked to an existing account by email only when Google says the email is
  verified. Facebook doesn't promise that, so a Facebook sign-in for an email that already has
  an account is refused (`email_in_use`) instead of linked: otherwise anyone who added a
  victim's address to a Facebook account could take over the Karobar account.
- `next` is only followed when it is a path under `/app` or `/accept-invite` with no `//` or
  backslash.
- Disabled users can't sign in through a provider.

## Rate limiting and denial of service

| Layer | Limit |
|---|---|
| nginx `limit_req` | 20 requests/s per IP on `/api/`, 10/min on `/api/accounts/`, 30 connections per IP |
| DRF throttles | `anon` 60/min, `user` 600/min, `auth` 10/min, `health` 120/min (env overridable) |
| Request size | 2 MB body (nginx and Django), 1000 form fields, 10 files |
| Timeouts | nginx 10 s for headers and body, gunicorn 30 s, Celery 300 s hard limit |
| Pagination | Cursor pagination, 200 rows per page at most, so deep pages cost the same as the first |

Every view has a `throttle_scope` or falls under `anon`/`user`. Heavy work (PDFs, reports, payroll
runs, emails) is a Celery task, never a request. Throttle counters live in Redis.

When a TLS proxy sits in front of nginx, configure `set_real_ip_from` for it, otherwise every
client shares the proxy's address and the per-IP limits apply to all of them together.

## Injection

- SQL goes through the ORM. `raw()`, `extra()`, `cursor.execute()` with string formatting and
  f-string SQL are not allowed; Ruff's bandit rules (`S608`) flag them. The health check's
  `SELECT 1` is the only literal SQL.
- MySQL runs in strict mode (`STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, no zero dates) so bad
  data is an error, not a silent truncation.
- The API only accepts JSON (`JSONParser`), and every serializer field has a `max_length` or a
  numeric bound.

## Cross-site scripting

- React escapes everything it renders. `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`,
  `insertAdjacentHTML`, `eval`, `new Function` and `javascript:` URLs are ESLint errors.
- JSON-LD is written with `textContent` and serialized by `serializeJsonLd`, which escapes `<` so
  a value can't close the script element. A test covers it.
- Translations are rendered as text (`escapeValue: false` in i18next is safe only because React
  escapes; never feed a translation into an HTML sink).

## Content Security Policy

The frontend is served by nginx with:

```
default-src 'self'; script-src 'nonce-<random>' 'strict-dynamic'; style-src 'self' 'nonce-<random>';
img-src 'self' data:; font-src 'self'; connect-src 'self' https://www.google.com/recaptcha/;
worker-src 'self'; object-src 'none'; base-uri 'none';
form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests
```

Vite stamps `nonce="__CSP_NONCE__"` on every tag it writes (`html.cspNonce`). nginx replaces the
placeholder with `$request_id`, 32 random hex characters per response, and sends the same value in
the header. HTML is `no-cache`, so a nonce is never reused. `strict-dynamic` lets the nonced entry
script load its lazy page chunks without listing them. reCAPTCHA needs `connect-src` for its `clr` call;
blocking that leaves tokens working but can lower people's scores, so real users meet the checkbox.

The service worker stores only the app's own code, never `/api/` responses, so nothing about a
business is left on a shared computer. Its stored page keeps the response headers it was fetched
with, so the nonce in that page still matches its CSP when it runs offline.

Fonts are self-hosted through Fontsource. The only third-party origins are Google's reCAPTCHA
ones, on the sign-in, sign-up and reset forms: the script is added by our nonced code, so
`strict-dynamic` admits it without a host list, and its iframes are allowed by
`frame-src https://www.google.com/recaptcha/ https://recaptcha.google.com/recaptcha/`. Adding
another origin (analytics, a CDN, a map) needs a line in this file and in
`deploy/nginx/snippets/html.conf`.

The Django side (admin, API errors) sends its own CSP through `django-csp`, also nonce based.

## Other headers

HSTS with preload (one year), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Cross-Origin-Opener-Policy: same-origin`,
`Cross-Origin-Resource-Policy: same-origin` on the API, a `Permissions-Policy` that turns off
camera, microphone, location, payment and USB, and `Cache-Control: no-store` on every API
response. `/app` and the sign-in screens also get `X-Robots-Tag: noindex`.

## Concurrency and race conditions

- MySQL runs at `READ COMMITTED`. Correctness under concurrency comes from explicit row locks,
  not from snapshot isolation.
- Anything read, checked and then written (stock levels, numbering series, balances, credit
  limits) runs inside `transaction.atomic()` and locks its rows with
  `apps.platform.locking.lock_rows()`, which refuses to run outside a transaction and always
  locks in primary-key order. One global lock order means two transactions can't deadlock on
  the same rows.
- `innodb_lock_wait_timeout` is 10 s, so a stuck lock fails a request instead of piling up.
- Never `INSERT IGNORE` (or `bulk_create(ignore_conflicts=True)`) a row that may already exist and
  then lock it: the ignored insert takes a shared lock, and two transactions holding shared locks
  while waiting for exclusive ones deadlock. Insert only the rows that are missing.
- Deadlocks that remain (two first-ever receipts creating the same stock level) are retried by
  `retry_on_deadlock`, which reruns the whole outermost transaction, as MySQL recommends.
- Document numbers come from a locked `NumberSeries` row in the same transaction as the posting,
  so a rolled-back post leaves no gap and two documents can't share a number. A test posts six
  entries from six threads at once and checks the numbers are 1 to 6.
- Stock: two threads issue the last unit at the same moment; exactly one succeeds and stock never
  goes below zero (the database also has a `quantity >= 0` check).
- Posting locks the entry (so it can't be posted twice) and the fiscal period row (so closing a
  period and posting into it can't interleave).
- Uniqueness is enforced by database constraints, not by "check then insert".
- Celery tasks are acknowledged late and must be idempotent: a task that runs twice must not post
  twice.

## Exports

CSV exports pass every cell through `apps.platform.csv_export.safe_cell`: text starting with
`=`, `+`, `-`, `@`, tab or carriage return gets a leading apostrophe, so a name like
`=HYPERLINK(...)` is shown as text instead of running as a spreadsheet formula. Numbers are
written as numbers. Files start with a UTF-8 byte order mark so Excel keeps Urdu and Arabic intact.

## Errors and logging

- Unhandled exceptions are logged with their traceback and answered with
  `{"detail": "Something went wrong.", "request_id": ...}`. Nothing else reaches the client.
- Every log line and every error body carries the request id. Incoming `X-Request-ID` values are
  accepted only if they match `[A-Za-z0-9-]{8,64}`, so clients can't inject text into logs.
- Never log passwords, tokens, cookies or full request bodies.

## Secrets and supply chain

- Secrets come only from environment variables (`backend/.env`, `deploy/.env`), which are git
  ignored. `.env.example` files list the names with empty or obviously fake values.
- Third-party secrets: `RESEND_API_KEY` (email, sent over Resend's SMTP relay so no SDK is
  needed), the two `RECAPTCHA_*_SECRET_KEY`s, `GOOGLE_OAUTH_CLIENT_SECRET` and
  `FACEBOOK_APP_SECRET`. Site keys and client ids are public and reach the browser through
  `GET /api/accounts/config/`; secrets never leave the server.
- The admin lives at `DJANGO_ADMIN_URL`, not `/admin/`.
- Containers run as non-root users, with read-only root filesystems and `no-new-privileges` in
  production.
- Dependencies are pinned to exact versions; Dependabot proposes updates; CI runs CodeQL and
  `npm audit`. A new dependency needs a reason in its pull request.

## Signed bill links

A customer can open one posted bill without an account through `/api/public/bills/<token>/`. The token is signed with `django.core.signing` under its own salt, names the business and the bill, and stops working after 30 days. A changed, old or draft link all answer 404. The response carries `Cache-Control: private, no-store`, `X-Robots-Tag: noindex` and `Referrer-Policy: no-referrer`, because the link is the key to the bill. Anyone holding the link can read that one bill until it expires, so it must only go to the customer. A link can't be withdrawn early except by rotating `SECRET_KEY`.

## Business chat

The chat () sends the question, recent messages and the figures the person's role may see to Groq, an outside service. People are told this in the chat. A key in  switches it on; without one it stays off.

- **It can only talk.** No code path from a reply reaches a record, so a clever message or a product name written as an instruction can't change anything. Replies are shown as plain text.
- **What it knows follows the role.**  includes sales and profit only with the reports permission and low stock only with inventory. Each person sees only their own chat, even within a business.
- **Every message is signed.** Each row carries an HMAC-SHA256 over the business, the person, the words, the time and the signature before it (). Editing, removing, inserting or moving a message breaks the chain, and the chat's check button finds it.
- **What the signature does not prove.** It shows the log has not changed since the server wrote it, and which signed-in account sent each message. It can't show who was at the keyboard, and it is not a legal electronic signature. The server holds the key, so someone with the key and the database could rewrite a whole chain.

Keep  set and stable in production. It defaults to , so rotating that without it makes old chats fail the check.
