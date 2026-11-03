# Project status

Last updated: 2026-11-03. Update at the end of every work session.

## Where we are

- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core), `v0.3.0` (M3 inventory).
  The Ledger Noir design, the floating navbar, the new footer and the ledger-opening intro are
  on `main`.
- PR #19 (`feat/design-pass-2`) is open with CI green: richer pages, module cards, redesigned
  auth, and fixes for all 13 CodeRabbit findings (FIFO layer rounding, stock on hand doubled by
  packs in search, exact barcode picks, live reduced-motion, focus and invite copy). Its review
  threads still need resolving on GitHub before the ruleset lets it merge. SonarCloud flags
  3.9% duplication; it is not a required check.
- M4 part 1, purchasing, is on `feat/m4-purchasing` (stacked on #19):
  - `apps/core`: `documents.line_amount` and `documents.share` (running-total slices), and the
    `supplier_bill` posting rule, at 100% branch coverage.
  - `apps/purchasing`: suppliers with balances; purchase orders (PO- numbers on confirm, closed
    when fully received); goods receipts posted through the inventory engine against GRNI;
    supplier bills clearing GRNI with purchase price variance, plus expense lines; supplier
    payments allocated to bills under row locks, the rest as an advance.
  - New chart roles `grni` (2160) and `purchase_variance` (5300), with a migration for
    existing businesses.
  - Screens: suppliers, purchase orders, goods received, bills, payments.
  - 232 backend tests, including two payments racing to settle one bill.
- M3 (inventory), merged in #18:
  - `apps/core`: moving-average and FIFO valuation, unit conversion, stock posting rules, at
    100% branch coverage.
  - `apps/inventory`: units, categories, products with variants, packs and barcodes,
    warehouses, batches with expiry, stock levels under row locks, FIFO cost layers, stock
    entries (receipt, issue, transfer, count) posted with gapless GRN/GIN/TRF/ADJ numbers and
    their cost posted to the books, low-stock and expiry alerts with a daily Celery email.
  - Screens: products, stock entries with a line editor, stock on hand with value, alerts, setup.
  - 179 backend tests, including two cashiers selling the last unit at once and three
    first-ever receipts racing to create a stock level.
- `npm run dev` now also runs Celery beat for scheduled jobs.

## Next session

1. Resolve the review threads on #19 and merge it; then rebase `feat/m4-purchasing` onto
   `main` and merge the purchasing PR.
2. M4 part 2, sales: customers with credit limits, quotations, orders, invoices, receipts,
   returns and credit notes, through the same document pattern.
3. M4 part 3: PDF invoices and receipts, statements, receivables and payables ageing.
   Purchase returns (debit notes) belong here too.

## Open questions

- First tax and payroll rules to ship (Pakistan first, then the Gulf), with official sources.
