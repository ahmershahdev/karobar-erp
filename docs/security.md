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
- Passwords: Argon2id first in `PASSWORD_HASHERS` (PBKDF2 kept only to verify and upgrade old
  hashes), at least 12 characters, common and numeric-only passwords rejected.
- Sign-in answers the same message for an unknown email and a wrong password. Django runs the
  hasher for unknown users too, so timing doesn't reveal which emails exist.

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
img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none';
form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests
```

Vite stamps `nonce="__CSP_NONCE__"` on every tag it writes (`html.cspNonce`). nginx replaces the
placeholder with `$request_id`, 32 random hex characters per response, and sends the same value in
the header. HTML is `no-cache`, so a nonce is never reused. `strict-dynamic` lets the nonced entry
script load its lazy chunks (three.js, pages) without listing them.

Fonts are self-hosted through Fontsource; there are no third-party origins. Adding one (analytics,
a CDN, a map) needs a line in this file and in `deploy/nginx/snippets/html.conf`.

The Django side (admin, API errors) sends its own CSP through `django-csp`, also nonce based.

## Other headers

HSTS with preload (one year), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Cross-Origin-Opener-Policy: same-origin`,
`Cross-Origin-Resource-Policy: same-origin` on the API, a `Permissions-Policy` that turns off
camera, microphone, location, payment and USB, and `Cache-Control: no-store` on every API
response. `/app` also gets `X-Robots-Tag: noindex`.

## Concurrency and race conditions

- MySQL runs at `READ COMMITTED`. Correctness under concurrency comes from explicit row locks,
  not from snapshot isolation.
- Anything read, checked and then written (stock levels, numbering series, balances, credit
  limits) runs inside `transaction.atomic()` and locks its rows with
  `apps.platform.locking.lock_rows()`, which refuses to run outside a transaction and always
  locks in primary-key order. One global lock order means two transactions can't deadlock on
  the same rows.
- `innodb_lock_wait_timeout` is 10 s, so a stuck lock fails a request instead of piling up.
- Document numbers must come from a locked counter row in the same transaction as the document
  (M2), so a rolled-back document leaves no gap and two documents can't share a number.
- Uniqueness is enforced by database constraints, not by "check then insert".
- Celery tasks are acknowledged late and must be idempotent: a task that runs twice must not post
  twice.

## Errors and logging

- Unhandled exceptions are logged with their traceback and answered with
  `{"detail": "Something went wrong.", "request_id": ...}`. Nothing else reaches the client.
- Every log line and every error body carries the request id. Incoming `X-Request-ID` values are
  accepted only if they match `[A-Za-z0-9-]{8,64}`, so clients can't inject text into logs.
- Never log passwords, tokens, cookies or full request bodies.

## Secrets and supply chain

- Secrets come only from environment variables (`backend/.env`, `deploy/.env`), which are git
  ignored. `.env.example` files list the names with empty or obviously fake values.
- The admin lives at `DJANGO_ADMIN_URL`, not `/admin/`.
- Containers run as non-root users, with read-only root filesystems and `no-new-privileges` in
  production.
- Dependencies are pinned to exact versions; Dependabot proposes updates; CI runs CodeQL and
  `npm audit`. A new dependency needs a reason in its pull request.
