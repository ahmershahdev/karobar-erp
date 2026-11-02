# Project status

Last updated: 2026-11-02. Update at the end of every work session.

## Where we are

- M1 is done and released as `v0.1.0`. The Ledger Noir redesign is merged.
- M2 (accounting core) is complete on `feat/m2-accounting-core`:
  - `apps/core`: posting rules (sale, purchase, receipt, payment, reversal) in account roles,
    fiscal period maths and balance sides, all at 100% branch coverage.
  - `apps/accounting`: standard chart of accounts installed for every new business (signal),
    fiscal years with monthly periods and closing, gapless JV numbering from a locked series,
    drafts, posting, reversals, immutability in the model, trial balance and general ledger
    with CSV export safe from formula injection.
  - Screens: journal with a line editor and live balance, chart of accounts, trial balance,
    general ledger, fiscal periods. English, Urdu and Arabic.
  - 128 backend tests, including six threads posting at once with no duplicate or missing
    numbers; every new route is in the tenant isolation tests.
- Existing businesses got their books with `python manage.py set_up_books` (safe to rerun).

## Next session

1. Merge the M2 pull request after CI; tag `v0.2.0`.
2. Start M3 (inventory): products, units, warehouses, stock moves under row locks, FIFO and
   moving-average valuation in `apps/core`, posting cost to the books through the posting rules.

## Open questions

- First tax and payroll rules to ship (Pakistan first, then the Gulf), with official sources.
