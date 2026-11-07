# AGENTS.md

Guide for coding agents and contributors. Short on purpose: details live in `docs/`, read only when
a task needs them. When a decision changes, update the matching doc in the same PR.

Karobar ERP: a multi-tenant ERP for small shops and distributors (inventory, sales and POS,
purchasing, double-entry accounting, tax reports, HR and payroll) in English, Urdu and Arabic.
Owner: Syed Ahmer Shah, <https://ahmershah.dev>, support@ahmershah.dev. Goes live at
`karobarerp.ahmershah.dev`.

## Read on demand

| Task touches | Read |
|---|---|
| Starting a session | [docs/status.md](docs/status.md) |
| What is done and what is left | [docs/roadmap.md](docs/roadmap.md) |
| Modules, data model, tenancy, posting rules, every decision | [docs/architecture.md](docs/architecture.md) |
| Auth, headers, CSP, rate limits, locking, anything an attacker touches | [docs/security.md](docs/security.md) |
| Public pages, meta tags, structured data, sitemap, llms.txt | [docs/seo.md](docs/seo.md) |
| Look, motion, colours, components | [docs/design.md](docs/design.md) |

## Stack

Python 3.12, Django 5.2, Django REST Framework, drf-spectacular, Celery, MySQL 8.4 (utf8mb4,
InnoDB; never SQLite, even in tests), Redis, WeasyPrint. React, TypeScript (strict), Vite,
Tailwind CSS, TanStack Query and Table, Recharts, i18next, anime.js. pytest, factory_boy, Vitest. Ruff, mypy
(strict), ESLint, Prettier. Docker Compose for dev and prod.

## Layout

```
backend/config/       settings/{base,dev,test,prod}.py, urls, celery
backend/apps/core/    pure business logic (posting rules, stock valuation, tax and payroll maths):
                      no Django imports, 100% branch coverage
backend/apps/platform/ cross-cutting web concerns: health, security headers, throttles, errors
backend/apps/accounts/ the user model and sign-in flows
backend/apps/tenancy/ tenants, members, roles and permissions, tenant scoping, audit log
backend/apps/{accounting,inventory,purchasing,sales,pos,hr,payroll,reports,assistant}/
backend/tests/        mirrors apps/
frontend/             React app: src/{app,pages,features,components,lib,i18n,styles}
deploy/               nginx and production compose
frontend/build/       build plugin: SEO files, service worker, compression
docs/                 roadmap, architecture, status
```

## Hard rules

- `apps/core` is plain Python; views, serializers and tasks only call it.
- Every tenant-owned model has `tenant` and is queried through the tenant-scoped manager.
  Another tenant's row is `404`, never `403`. Every new endpoint goes into the isolation tests.
- Money and quantities are `Decimal` (`DecimalField`), never `float`. Rounding happens in one
  place in `apps/core`.
- Posted documents and journal entries are immutable. Corrections are reversals or credit notes.
- Every journal entry balances (debits equal credits) before it is saved; the database
  transaction covers the document, its stock moves and its journal entry together.
- Stock changes only through stock moves. Stock levels are updated under `select_for_update`.
- Document numbers (invoice, bill, receipt) are per tenant, per series and without gaps.
- Tax rates, payroll tax slabs and holidays are data with a source and a validity period, never
  constants in code.
- Every create, update, post and delete on business data writes an audit log row.
- Secrets only from environment variables. Never commit `.env`, dumps, keys or real customer,
  supplier or employee data. Seed data is invented.
- API changes update the OpenAPI schema and the frontend types in the same PR.
- No new dependency without a reason in the PR. Pin exact versions.
- The maintainer reviews `apps/core` and must be able to explain every line of it.
- No emojis in code, UI text or docs.
- Write for someone who doesn't read comfortably: plain words first, a picture beside every screen
  name, one short sentence on what happened and what to do next. See `docs/design.md`.
- New UI text goes into all three locale files in the same PR; a test compares their keys.
- No hardcoded hosts, URLs or keys: the API base, the public site URL and every secret come from
  environment variables (`VITE_*` for the frontend, read in one module each side).

## Security rules

Details and the reasoning are in [docs/security.md](docs/security.md). The short version:

- SQL only through the ORM. No `raw()`, `extra()` or string-built SQL; Ruff's `S608` stays on.
- No `dangerouslySetInnerHTML`, `eval` or `new Function` in the frontend; ESLint blocks them.
  The JSON-LD component is the one exception and escapes `<`.
- Session cookies (HttpOnly, Secure, SameSite=Lax) and Django CSRF for the SPA. No tokens in
  `localStorage`.
- Passwords hashed with Argon2id, bcrypt as the runtime fallback, never in the browser; minimum
  length 12; common and all-numeric passwords rejected.
- Content Security Policy with a per-request nonce and `strict-dynamic`; no `unsafe-inline` for
  scripts. New third-party origins need a line in `docs/security.md`.
- A new top-level app screen goes in `AUTH_PATHS` and in nginx, or it answers 404 in production.
- Every endpoint has a throttle scope. Sign-in, sign-up and password reset have strict ones.
- Request body, page size and upload sizes are capped; slow work goes to Celery.
- The service worker stores code only. `/api/` responses are never cached.
- Never hide anything with a large negative offset; in RTL it widens the page. Use `sr-only`.
- Anything read-then-written under concurrency (stock, numbering, balances) runs inside
  `transaction.atomic()` with `select_for_update()`, in a fixed lock order (by primary key).
- Errors never leak stack traces, SQL or another tenant's identifiers.

## SEO rules

Public pages only; everything under `/app` is `noindex`. See [docs/seo.md](docs/seo.md).

- Every public route has a title under 60 characters, a description under 160, a canonical URL,
  Open Graph and Twitter tags, and JSON-LD (including a `BreadcrumbList`). A test enforces the
  lengths.
- `robots.txt`, `sitemap.xml`, `llms.txt` and `llms-full.txt` are generated at build time from
  the route list and `VITE_SITE_URL`; never edit copies by hand. The same build writes `sw.js` and
  the `.br` and `.gz` files.

## Design rules

See [docs/design.md](docs/design.md). White, minimal, easy to use. Colours, radii and motion timings
are tokens in `frontend/src/styles/tokens.css`; components never use raw hex values. Text colours
keep AA contrast. Logos go through `components/Logo.tsx`. All motion honours
`prefers-reduced-motion`, and the app screens favour speed and clarity over effects.

## Comments

Default is no comment. Write one only for what the code can't say: why it's done this way, an
accounting or tax rule with its source, or a trap for the next person. Not: restating the code,
section banners, history, owner-less TODOs, or filler (simply, robust, seamless, ensure, leverage,
comprehensive). Write comments the way you'd explain it to a colleague: plain sentences, no
headings, no decoration.

## Workflow

- Branches `feat/...`, `fix/...`, `docs/...`, `chore/...`. `main` takes PRs only, squash-merged.
- Each PR belongs to a milestone and closes its issue when there is one.
- Commit messages: short, imperative, no prefixes.
- Releases: `v0.x` pre-releases until launch, `v1.0.0` at launch; tag the merge commit, then
  `gh release create vX.Y.Z --verify-tag --generate-notes` (add `--prerelease` before 1.0).
- Update `docs/status.md` at the end of every session.
