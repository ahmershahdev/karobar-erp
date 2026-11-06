# Project status

Last updated: 2026-11-06. Update at the end of every work session.

## Where we are

- New look, uncommitted on `feat/brand-theme`: a minimal white theme replaces the dark brand theme
  of #22 across the site and app (see `docs/design.md`). The real logo is now used everywhere as
  WebP, and the source PNG is gone from the repo root (still in git history). Removed: WebGL
  particles and `three`, Montserrat, the custom cursor, grain, marquee, tilt cards, the pinned
  module gallery and the curtain transition. Also fixed: the sign-up honeypot's negative offset
  made RTL pages about 10,000px wide.
- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core), `v0.3.0` (M3 inventory).
  The Ledger Noir design, the floating navbar, the new footer and the ledger-opening intro are
  on `main`.
- PR #19 (`feat/design-pass-2`) is open: richer pages, module cards, redesigned auth, the FIFO
  rounding fix, and a cleanup that moves the table class strings to `workspace/table.ts`, the
  local-date helper to `lib/dates.ts`, and both modules onto the shared `useTenantAction` hook.
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

- Open and stacked: #20 (M4 purchasing, on #19), #21 (Resend, reCAPTCHA v3 and v2, honeypot,
  Google and Facebook sign-in, on #19), #22 (brand theme from the logo: navy, azure and ember,
  Montserrat, new mark, preloader, curtain page transition, cursor, footer, on #21).
- Google sign-in is configured in the Google Cloud project "Karobar ERP"
  (`storied-catwalk-513610-u1`, in testing mode with the owner's Gmail as test user); a duplicate
  empty "Karobar ERP" project was created by mistake and can be deleted. Facebook is waiting for
  the owner to sign in at developers.facebook.com.

## Next session

1. Merge PR #19 after CI.
2. Start M4 (purchasing and sales): suppliers, purchase orders, goods received, bills and
   payments; customers, quotations, orders, invoices, receipts, returns and credit notes; each
   posting its stock moves and journal entry in one transaction through the posting rules.

## Open questions

- First tax and payroll rules to ship (Pakistan first, then the Gulf), with official sources.
