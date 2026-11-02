# Project status

Last updated: 2026-11-03. Update at the end of every work session.

## Where we are

- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core). The Ledger Noir design,
  the floating navbar, the new footer and the ledger-opening intro are on `main`.
- M3 (inventory) is complete on `feat/m3-inventory`:
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

1. Merge the M3 pull request after CI; tag `v0.3.0`.
2. Start M4 (purchasing and sales): suppliers, purchase orders, goods received, bills and
   payments; customers, quotations, orders, invoices, receipts, returns and credit notes; each
   posting its stock moves and journal entry in one transaction through the posting rules.

## Open questions

- First tax and payroll rules to ship (Pakistan first, then the Gulf), with official sources.
