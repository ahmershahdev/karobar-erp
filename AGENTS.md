# AGENTS.md

Guide for coding agents and contributors. Short on purpose: details live in `docs/`, read only when
a task needs them. When a decision changes, update the matching doc in the same PR.

Karobar ERP: a multi-tenant ERP for small shops and distributors (inventory, sales and POS,
purchasing, double-entry accounting, tax reports, HR and payroll) in English, Urdu and Arabic.
Owner: Syed Ahmer Shah, <https://ahmershah.dev>, support@ahmershah.dev. Goes live at
`karobar.ahmershah.dev`.

## Read on demand

| Task touches | Read |
|---|---|
| Starting a session | [docs/status.md](docs/status.md) |
| What is done and what is left | [docs/roadmap.md](docs/roadmap.md) |
| Modules, data model, tenancy, posting rules, every decision | [docs/architecture.md](docs/architecture.md) |

## Stack

Python 3.12, Django 5.2, Django REST Framework, drf-spectacular, Celery, MySQL 8.4 (utf8mb4,
InnoDB; never SQLite, even in tests), Redis, WeasyPrint. React, TypeScript (strict), Vite,
Tailwind CSS, TanStack Query and Table, Recharts, i18next. pytest, factory_boy, Vitest. Ruff, mypy
(strict), ESLint, Prettier. Docker Compose for dev and prod.

## Layout

```
backend/config/       settings/{base,dev,test,prod}.py, urls, celery
backend/apps/core/    pure business logic (posting rules, stock valuation, tax and payroll maths):
                      no Django imports, 100% branch coverage
backend/apps/tenancy/ tenants, members, roles and permissions, tenant scoping, audit log
backend/apps/{accounting,inventory,purchasing,sales,pos,hr,payroll,reports}/
backend/tests/        mirrors apps/
frontend/             React app
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

## Comments

Default is no comment. Write one only for what the code can't say: why it's done this way, an
accounting or tax rule with its source, or a trap for the next person. Not: restating the code,
section banners, history, owner-less TODOs, or filler (simply, robust, seamless, ensure, leverage,
comprehensive).

## Workflow

- Branches `feat/...`, `fix/...`, `docs/...`, `chore/...`. `main` takes PRs only, squash-merged.
- Each PR belongs to a milestone and closes its issue when there is one.
- Commit messages: short, imperative, no prefixes.
- Releases: `v0.x` pre-releases until launch, `v1.0.0` at launch; tag the merge commit, then
  `gh release create vX.Y.Z --verify-tag --generate-notes` (add `--prerelease` before 1.0).
- Update `docs/status.md` at the end of every session.
