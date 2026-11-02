# Architecture

The platform skeleton (M1) is in place; the business modules are still design. Change this file in
the same pull request that changes the code.

## Parts

```
browser ──> nginx (static app, CSP nonce, rate limits) ──> Django + DRF (gunicorn)
                                                              │  ──> MySQL 8.4 (all tenants, one schema)
                                                              │  ──> Redis (cache, throttles, Celery queue)
                                                              v
                                                         Celery workers ──> PDFs, emails, alerts, reports
```

The app and the API share one origin: nginx serves the built React app and proxies `/api/`. That
keeps cookies first-party and removes CORS entirely.

The web app only calls the API. Long work (PDF batches, alerts, big reports, payroll runs) runs in
Celery, never inside a web request.

## Modules

| App | Owns |
|---|---|
| `tenancy` | tenants, members, roles, permissions, invitations, audit log |
| `accounting` | accounts, fiscal periods, journal entries, numbering series |
| `inventory` | products, units, warehouses, stock moves, stock levels, batches |
| `purchasing` | suppliers, purchase orders, goods received, bills, supplier payments |
| `sales` | customers, quotations, orders, invoices, receipts, returns, credit notes |
| `pos` | registers, sessions, counter sales |
| `hr`, `payroll` | employees, attendance, leave, salary structures, payroll runs, payslips |
| `reports` | trial balance, P&L, balance sheet, tax and stock reports |
| `core` | pure logic used by all of the above (posting rules, valuation, tax, payroll maths) |
| `platform` | health check, request ids, security headers, error handler, pagination, row locking |
| `accounts` | the user model (email sign-in, public UUID) and the session endpoints |

## Frontend layout

```
frontend/src/
  app/        router and shell
  pages/      one file per route, lazy loaded except home
  features/   pieces with their own logic (hero shader, ledger demo, module grid)
  components/ shared UI (header, footer, reveal, page transition, breadcrumbs)
  lib/        env, API client, SEO hooks, motion helpers
  i18n/       en, ur, ar
  seo/        route list and JSON-LD, shared with the build
  styles/     tokens.css and global.css
```

API types in `src/lib/api/schema.d.ts` are generated from `backend/openapi.yaml`
(`npm run api:types`); CI fails if either is stale.

## Tenancy

One database and one schema. Every tenant-owned table has a `tenant_id` column, first in its
indexes. Models use a manager that filters by the current tenant; the request's tenant comes from
the `X-Tenant` header (the tenant's public UUID), which the app's tenant switcher sets; the
middleware checks membership before activating it. Rows of another tenant answer `404`. An isolation test calls every
endpoint as a member of another tenant.

## Data model (first draft)

```
tenant            id, name, base_currency, valuation_method, fiscal_year_start, locale
member            tenant_id, user_id, role_id
role              tenant_id, name, permissions (module x action)
audit_event       tenant_id, user_id, action, model, object_id, changes (JSON), at

account           tenant_id, code, name, type (asset, liability, equity, income, expense), parent_id
fiscal_period     tenant_id, start, end, closed
journal_entry     tenant_id, number, date, source_type, source_id, posted_at, reversal_of
journal_line      entry_id, account_id, debit, credit, party_id

product           tenant_id, sku, name, unit_id, tax_rate_id, track_batches
stock_move        tenant_id, product_id, warehouse_id, batch_id, qty, unit_cost, source_type, source_id
stock_level       tenant_id, product_id, warehouse_id, qty, value      (locked on update)
cost_layer        tenant_id, product_id, warehouse_id, qty_left, unit_cost  (FIFO)

invoice / bill    tenant_id, number, party_id, date, status, totals; lines with qty, price, tax
tax_rate          tenant_id, name, rate, valid_from, valid_to
```

## Posting

A document is posted in one database transaction: lock the stock levels it touches, write the
stock moves, write the journal entry, then mark the document posted. If any step fails, nothing
is saved. Posting rules (which accounts a sale, a purchase, a return or a payroll run debits and
credits) live in `apps/core` as plain functions with full test coverage.

## Decisions

| Decision | Why |
|---|---|
| Django + DRF + MySQL | The admin, ORM, migrations and permissions fit an ERP; the same stack as HolidayOps |
| One schema with `tenant_id` | Simple to run and migrate; isolation is enforced in code and proven by tests |
| MySQL in tests, never SQLite | Row locks, decimal and collation behaviour must match production |
| `Decimal` everywhere, rounding in one place | Floats lose cents; scattered rounding makes totals disagree |
| Immutable posted documents | Accounting needs an audit trail; corrections are reversals and credit notes |
| Row locks on stock levels | Two cashiers selling the last item must not both succeed |
| Tax rates and payroll slabs as dated data | They change by law every year; old documents keep their old rates |
| Session cookies, not JWTs | HttpOnly cookies can't be read by injected script; CSRF is solved by Django |
| `X-Tenant` header, not subdomains | One certificate and one origin; a user with several businesses switches without signing in again |
| Cursor pagination | Constant cost per page on large tables; no `OFFSET` scans |
| `READ COMMITTED` plus explicit locks | Fewer gap-lock deadlocks than `REPEATABLE READ`; locks say exactly what is protected |
| Fail-closed tenant manager | A forgotten filter raises instead of leaking every tenant's rows |
| Per-route HTML generated at build | Crawlers and link previews get the right head without server rendering |

## Open questions

- Which chart of accounts template to start from, and which tax and payroll rules to ship first
  (Pakistan, then Gulf countries); each needs official sources before it is coded.
- Whether HR uses the `holidays` library directly or the HolidayOps API for working days.
