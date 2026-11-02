# Architecture (planned)

This is the design before any code. Change it in the same pull request that changes the code.

## Parts

```
React web app  ──>  Django + DRF API  ──>  MySQL 8.4 (all tenants, one schema)
                         │           ──>  Redis (Celery queue, cache)
                         v
                    Celery workers   ──>  PDFs, emails, alerts, heavy reports
```

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

## Tenancy

One database and one schema. Every tenant-owned table has a `tenant_id` column, first in its
indexes. Models use a manager that filters by the current tenant; the request's tenant comes from
the member's chosen business. Rows of another tenant answer `404`. An isolation test calls every
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

## Open questions

- How a user picks the tenant: a tenant switcher with a header on each request, or one subdomain
  per tenant.
- Which chart of accounts template to start from, and which tax and payroll rules to ship first
  (Pakistan, then Gulf countries); each needs official sources before it is coded.
- Whether HR uses the `holidays` library directly or the HolidayOps API for working days.
