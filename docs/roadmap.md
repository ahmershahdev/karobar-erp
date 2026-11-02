# Roadmap

Each milestone is a set of small pull requests into `main`. A milestone is done when its
checklist is ticked, CI is green and [status.md](status.md) is updated. Each module ships with its
screens in the same milestone. Target dates are plans, not deadlines; GSoC, Outreachy and
upstream pull requests come first.

Done for the whole project means: a live demo, a README with setup steps and screenshots, tests
in CI, and seed data.

## M1. Platform skeleton (target 2026-11-29)

- [x] Django project, settings per environment (`dev`, `test`, `prod`), health endpoint
- [x] MySQL 8.4, Redis and one Celery worker in Docker Compose (MySQL in tests too, never SQLite)
- [x] pytest with coverage, Ruff, mypy (strict); Vite + React + TypeScript app with Vitest, ESLint
- [x] GitHub Actions: `backend`, `frontend`, CodeQL
- [x] Make `backend`, `frontend` and CodeQL required checks in the ruleset
- [x] Dependabot for Actions, Python, npm and Docker
- [x] Accounts: sign up, sign in, password reset, email verification
- [x] Tenants and members, roles with permissions per module, invitations
- [x] Tenant-scoped managers and an isolation test that runs against every endpoint
- [x] Audit log for every change to business data (each later module records through `apps.tenancy.audit`)
- [x] English, Urdu and Arabic in the app shell, right to left for Urdu and Arabic

- [x] Security baseline: Argon2id, CSRF on sign-in, nonce CSP, rate limits, row-lock helper
- [x] `npm run dev` at the repository root starts MySQL, Redis, Django, Celery and Vite
- [x] Public site with SEO (per-route heads, JSON-LD, sitemap, robots, llms.txt) and the design system

## M2. Accounting core (target 2026-12-20)

- [x] Chart of accounts from a template, editable per tenant
- [x] Fiscal years and periods; a closed period takes no new entries
- [x] Journal entries: balanced before saving, immutable once posted, reversals
- [x] Posting rules in `apps/core` that every later module uses
- [x] Gapless document numbering per tenant and series
- [x] Trial balance and general ledger with filters and CSV export

## M3. Inventory (target 2027-01-10)

- [x] Products, variants, units and conversions, categories, barcodes
- [x] Warehouses and stock moves (receipt, issue, transfer, adjustment)
- [x] Stock levels updated under row locks; a concurrency test with parallel sales of the last item
- [x] Valuation by FIFO and moving average, chosen per tenant, with cost posted to the books
- [x] Batches with expiry dates; low-stock and expiry alerts (Celery)

## M4. Purchasing and sales (target 2027-01-31)

- [ ] Suppliers, purchase orders, goods received, supplier bills, supplier payments
- [ ] Customers, quotations, sales orders, invoices, receipts, returns and credit notes
- [ ] Customer credit limits checked on order and invoice
- [ ] Each document posts its stock moves and journal entry in one transaction
- [ ] PDF invoices and receipts (WeasyPrint) in English, Urdu and Arabic
- [ ] Customer and supplier statements, receivables and payables ageing

## M5. Point of sale, tax and reports (target 2027-03-14)

- [ ] POS screen: barcode scan, cart, cash and card payments, receipt print, end-of-day close
- [ ] Tax rates as data per tenant with validity dates; tax on every document line
- [ ] Sales tax (GST/VAT) report for a period
- [ ] Profit and loss, balance sheet and cash flow for any period
- [ ] Dashboard: sales, margins, stock value and top products (Recharts)
- [ ] Indexes and query checks for reports on 1 million document lines

## M6. HR and payroll (target 2027-04-11)

- [ ] Employees, departments, contracts and salary structures
- [ ] Attendance and leave on working days (weekends and public holidays from the `holidays` library)
- [ ] Monthly payroll: earnings, deductions, income tax from slabs stored as data per tax year
- [ ] Payslips as PDF; payroll posts its journal entry

## M7. Docs and launch (target 2027-06-13)

- [ ] Seed data: two invented businesses with a year of documents
- [ ] README setup steps and screenshots
- [ ] End-to-end tests with Playwright for the main flows
- [ ] Deploy at `karobarerp.ahmershah.dev`; tag `v1.0.0`
