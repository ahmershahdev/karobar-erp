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
| `accounting` (built) | accounts, fiscal years and periods, number series, journal entries and lines, trial balance and ledger reports |
| `inventory` (built) | units, categories, products and packs, warehouses, batches, stock levels, FIFO layers, stock entries and moves, alerts |
| `purchasing` (built) | suppliers, purchase orders, goods receipts, supplier bills and payments with their allocations |
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
| Posting rules speak in account roles | `sale()` debits "receivables", not account 1130; each tenant maps roles to its own chart, so rules work for every chart |
| Drafts may be unbalanced; posting may not | People enter entries in steps; the balance check, the open-period check and the number all happen at post time |
| Numbers assigned at post, from a locked series row | Drafts that are deleted never consume a number, and a rolled-back post returns its number, so the series has no gaps |
| Immutability enforced in the model too | `JournalEntry.save()` and `JournalLine.save()` refuse to change posted rows, so even admin scripts can't edit the books |
| Standard chart first, July fiscal year by default | A general small-business chart suits Pakistan and the Gulf; July to June is Pakistan's fiscal year, and each business can pick its month |
| One lock per product and warehouse | Batch levels and FIFO layers are only touched while their `StockLevel` row is locked, so one row lock guards all three |
| Costing method fixed per business | Moving average or FIFO is chosen when the business is created; switching later would revalue every past issue |
| Transfers carry cost, not value | A transfer posts no journal entry; the destination receives exactly the cost (and, under FIFO, the layers) that left the source |
| Counts post the difference | An adjustment line holds the counted quantity; posting books only what was found or lost |
| Goods receipts post through the inventory engine | A receipt creates and posts a stock receipt (Dr inventory, Cr GRNI), so locking, batches and FIFO layers have one implementation; the receipt shares its GRN number |
| Bills clear GRNI at the receipt's booked value | The bill takes the same value off GRNI that the receipt put on, in running-total slices (`core.documents.share`) so partial bills never strand a paisa; any price difference goes to purchase price variance, not back into stock that may already be sold |
| Unallocated supplier payments are advances | The whole payment debits payables; allocations only mark which bills it settles, so an overpayment shows as a debit balance on the supplier |
| Draft documents check their links when saved | A draft can't point at a draft order or an unposted receipt, so deleting one draft never fails on another's reference |
| Email through Resend's SMTP relay | `RESEND_API_KEY` becomes the SMTP password; Django's own backend sends, so there is no SDK to pin, and any other SMTP provider still works through `EMAIL_*` |
| reCAPTCHA v3 first, v2 only when needed | Most people never see a challenge; a low score or a failed check asks for the checkbox. The honeypot costs nothing and catches the simplest bots before Google is called |
| OAuth without a library | Two providers and one flow (authorization code, PKCE where supported) fit in one module that the maintainer can read end to end; the session stays the only credential |
| Facebook never links by email | Facebook doesn't say whether the email was verified, so linking by it would let a stranger take over an account |
| Business slugs are for addresses only | `/app/al-madina-traders` reads better than a UUID, but the API still takes `public_id` in `X-Tenant`. The app resolves a slug against the user's own memberships, so knowing one gives nothing away, and a slug never changes when a business is renamed, so links keep working. |
| Sign-in screens live at the root | `/login` and `/signup` are what people expect and can type. `/app` holds only the workspace. Old addresses redirect with their query string, because emails already sent still use them, and those words are reserved so no business can take them as a slug. New screens go in `AUTH_PATHS` in `lib/paths.ts` and in the nginx list: unknown addresses are real 404s. |
| Brotli without an nginx module | The official nginx image has no Brotli. The build writes `.br` and `.gz` files and nginx picks one with a `map`. Dynamic gzip must stay off for those locations: it can't see `add_header` and would compress the `.br` file again. |
| A service worker for offline, not offline data | It keeps the app's code so an offline visit gets a helpful screen rather than the browser's error. Business data is not cached: a shop's books must never look current when they aren't. |
| Books set up through a `tenant_created` signal | Tenancy doesn't import accounting; later modules hook in the same way |

## Open questions

- Which tax and payroll rules to ship first (Pakistan, then Gulf countries); each needs official
  sources before it is coded.
- Whether HR uses the `holidays` library directly or the HolidayOps API for working days.
