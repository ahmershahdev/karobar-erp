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

### Changing your own account

- Changing the password or the email needs the current password, so someone at an unlocked
  computer can't take the account over. Both use the tight `auth` throttle, because each one can
  be used to guess that password. A Google or Facebook account with no password is sent to
  Forgot password first.
- A new password signs out every other session, through Django's session hash, and keeps the
  one that made the change. The owner gets an email either way.
- A new email only takes effect from a signed link sent to the new address (`accounts.change-email`
  salt, one day). The link signs a fingerprint of the password hash, the email and when it was last
  confirmed, so any change of password or email ends every link sent before. Changing the password
  therefore stops an attacker's pending change, and a link can't work again after the email goes
  from A to B and back. It is checked again under a row lock, so it can't be used twice at once.
  The old address is told once the change is made.
- Asking for an address that already has an account gets the same answer as any other, and the
  owner of that address gets an email, so the form can't be used to find out who has an account.
- Emailed links carry their token in the query string, so nginx logs the path without the query
  and without the referrer (`log_format private`). Checked in the production image.

### Handing over a business and deleting an account

- Only the owner can make another member the owner (`transfer_ownership`). Both memberships are
  locked in key order and the owner flag is checked again under the lock, so two hand-overs at
  once can't leave two owners. The old owner stays a member with no role. Both changes are
  audited and the new owner gets an email.
- Deleting an account needs the current password and the person typing their own email. It is
  refused while they own any business, so a business is never left without an owner.
- The user row is never removed, because posted documents, journal entries and the signed chat
  must keep pointing at whoever made them. It is anonymised instead, under a row lock: the email
  becomes `former-user-<id>@karobar.invalid`, the name, password and linked Google or Facebook
  sign-ins are removed, and the account is switched off, which ends every session. Each
  membership is deleted with an audit row that names "a former member". The old address gets a
  last email and can sign up again.
- What stays: older audit rows and invitation records that already hold the address, such as
  "member removed", keep it, because the audit log is never edited. Decide before launch whether
  that needs a clean-up job for privacy rules.

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

## Employee records

HR screens and `/api/hr/` follow the `hr` module permission like every other module, and another business's employees answer 404. An employee record can hold a national identity number (CNIC or Emirates ID) and a bank account, because payroll tax and salary transfers need them. They are optional, shown only to people with HR rights, never sent to the business chat, and never printed on anything but what payroll will need later. Employees who have had a contract are marked as left instead of deleted, so payroll history keeps pointing at them; a nightly job (`apps/hr/tasks.clear_former_employee_details`) clears a former employee's bank account 90 days after they leave and their national ID six years after the end of the tax year they left in, which is how long tax records must be kept. The business can keep IDs longer, never shorter. The audit row records that a field was cleared, never its value.
## Bill pictures

The only file uploads are the logo and the signature picture on the Bill design screen (`/api/sales/bill-settings/logo/` and `/signature/`), open to people with update rights on members. Each file goes through these checks in order (`apps/sales/billing.clean_image`), and fails as one plain message:

1. The browser's stated type must be PNG, JPEG or WebP and the name must end in a matching extension. This is a first filter only, as both can be faked.
2. nginx refuses any request over 2 MB (`client_max_body_size`). Django's own upload limits don't count file data, so the view also refuses a request whose stated length is over 1 MB plus 64 KB before reading it, and reads the file only to one byte past 1 MB.
3. The first bytes must be a PNG, JPEG or WebP signature. A web page, script, program or GIF renamed to `.png` stops here.
4. Pillow is told to use only the decoder for that format, so a file can't pass as one format and be read by another, less careful decoder.
5. The claimed size is checked before decoding: each side 16 to 5000 pixels and at most 25 million pixels, so a small file that unpacks to a huge picture is refused. A picture with more than one frame (an animation) is refused.
6. `verify()` checks the file's structure, then a full decode refuses a damaged or cut-off file.
7. Only the pixels are kept: the picture is written out again as a fresh PNG, at most 600 by 600 for a logo and 600 by 200 for a signature. Metadata, scripts, or a second file hidden after the picture are all left behind, so a file built to attack a viewer or printer is harmless once stored.

The copy is stored in the database, shown as a `data:` URL, which the CSP already allows for images, and served back only to the same business with `Cache-Control: private, no-store`. Nothing is ever served from the original upload. There is no virus scanner: the uploads are never run or stored as sent, so the re-encoding above is the protection. If uploads of other kinds are added later, scan them (for example with ClamAV in the Docker setup) before keeping them.

The bill's accent colour goes into the print style sheet, so it is accepted only as `#` and six hex digits, and only when it reads on white at 4.5 to 1 or better (`apps/core/colours.py`).

## Signed bill links

A customer can open one posted bill without an account through `/api/public/bills/<token>/`. The token is signed with `django.core.signing` under its own salt, names the business and the bill, and stops working after 30 days. A changed, old or draft link all answer 404. The response carries `Cache-Control: private, no-store`, `X-Robots-Tag: noindex` and `Referrer-Policy: no-referrer`, because the link is the key to the bill. Anyone holding the link can read that one bill until it expires, so it must only go to the customer. A link can't be withdrawn early except by rotating `SECRET_KEY`.

## Business chat

The chat (`apps/assistant`) sends the question, recent messages and the figures the person's role may see to Groq, an outside service. People are told this in the chat. A key in `GROQ_API_KEY` switches it on; without one it stays off.

- **It can only talk and propose drafts.** No code path from a reply reaches a record. Replies are shown as plain text. Beyond that, the model can ask for one of three tools: a draft sales invoice, a draft quotation, or a draft purchase order (`apps/assistant/drafts.py`). It only sees the tools the person's role may `create` with, and a tool it names anyway becomes a "not allowed" card.
- **A draft is a card until the person confirms it.** The model gives names, never ids. The server looks each one up through the tenant-scoped managers, takes the unit, price and warehouse from the business's own records, and stores the result as a signed `draft` row. The card shows exactly what will be saved. Confirm (`/api/assistant/drafts/<id>/confirm/`) checks the permission again and runs the document's own serializer and save, so validation, audit and numbering match its screen, then writes a signed `done` row in the same transaction. A card can be confirmed once, only by the person it was shown to, and only in the current chat. Nothing in this path posts, pays, sends or deletes, so a product name written as an instruction can at worst put a draft card in front of someone who still has to press Confirm.
- **It keeps to the business.** The prompt tells it to answer only about the business and using Karobar, and to decline everything else. That is an instruction to a model, not a guarantee, so a determined person may still get an off-topic reply. No data or action depends on it.
- **A new chat hides, it never deletes.** Reset adds a signed `reset` row to the chain. Only rows after the last one are shown or sent to Groq. Older rows stay in the chain and are still checked, and removing a reset row is caught like any other removal, unless it is among the newest rows.
- **What it knows follows the role.** `facts()` includes sales and profit only with the reports permission, and low stock only with inventory. The read-only lookups (`apps/assistant/lookups.py`) follow the same rule: a product's price with sales or inventory view, its stock only with inventory view, customers with sales view, suppliers with purchasing view. They send names, codes, balances and recent documents, never phone numbers, emails or addresses. Lookup results go to Groq for that one answer and are not kept in the chat. One answer may make at most three lookups and must finish within 25 seconds. Each person sees only their own chat, even within a business. This covers new answers only: replies saved before someone lost a permission stay in their chat and still go to Groq as recent history. They hold nothing the person wasn't shown at the time, and they can't be edited because they are signed.
- **Every message is signed.** Each row carries an HMAC-SHA256 over the business, the person, the words, the time and the signature before it (`apps/core/chain.py`). Editing, inserting or moving a message breaks the chain, and so does removing any message except the newest, and the check button in the chat finds it. Deleting the newest messages is not found, because nothing signed after them refers to them: the rest is still a valid, shorter chain.
- **What the signature does not prove.** It shows the log has not changed since the server wrote it, and which signed-in account sent each message. It can't show who was at the keyboard, and it is not a legal electronic signature. The server holds the key, so someone with the key and the database could rewrite a whole chain.

Keep `CHAT_SIGNING_KEY` stable in production. Production refuses to start with a `GROQ_API_KEY` and no `CHAT_SIGNING_KEY`. Elsewhere it falls back to `SECRET_KEY`, so rotating that would make old chats fail the check.
