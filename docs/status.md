# Project status

Last updated: 2026-11-07. Update at the end of every work session.

## Where we are

- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core), `v0.3.0` (M3 inventory), `v0.4.0` (M4 purchasing, sales, documents), `v0.5.0` (M5 counter, tax, reports, report indexes).
- Merged since `v0.5.0`: the business home page (#32), signed bill links, WhatsApp click-to-chat and the daily summary email (#33), and the business chat through Groq with signed messages (#34, `apps/assistant`, `apps/core/chain.py`; see `docs/security.md`).
- Also merged: chat focus and new chat (#35), confirm before every delete (#36), name, email and password settings (#37), chat screen names per language (#38), and handing over a business and deleting an account (#39).
- Merged: chat drafts (#40). The chat can propose a draft sales invoice, quotation or purchase order as a card; the person presses Confirm and the document's own save runs with their permissions. It never posts, pays or deletes. See `docs/security.md`. Checked live against Groq with invented names: it returned the right tool calls. Not yet tried by a person in the browser.
- Merged: chat lookups (#41). The chat can look up a product (price, packs, stock), a customer (balance, recent invoices) or a supplier (balance, recent bills) when asked, limited to what the role may view. Checked live against Groq with an invented result.
- Merged: discounts (#42). Line and bill discounts on invoices, quotations and the counter, with a per-role limit and a Sales discounts account. Lines and the bill each take a percentage or an amount; the counter takes percentages.
- In review: `feat/hr-employees`, the first M6 piece: departments, salary structures (allowances and deductions as fixed amounts or a % of basic, with a monthly preview), employees and contracts that never overlap. No income tax or payroll run yet.
- Merged: the bill design (#43). A Bill design screen with six templates (classic, modern, minimal, bold, compact, elegant), logo, business details, title and number prefix (INV- by default), a signature typed or uploaded, footer, colour, columns and an 80 mm till roll for counter sales. Uploaded pictures go through the checks in `docs/security.md`. Printed bills, receipts and signed bill links all use it.
- In review, stacked on the employees PR: `feat/hr-attendance-leave`. The work week and public holidays (filled from the `holidays` library, editable), kinds of leave with yearly allowances, asking for and approving leave in working days, daily attendance, and the nightly job that clears former employees' bank accounts after 90 days and national IDs after six years.
- `feat/ai-assistant` is replaced by #33 and #34 and can be deleted.
- Page text for the business home lives under `business` in the locale files. The public home page owns `home`; mixing them crashed the home page once.
- `npm run dev` also runs Celery beat for scheduled jobs. Celery does not reload, so restart it after changing tasks or email code.
- PDFs need Pango, so they can't be made on the maintainer's Windows machine. Printing and signed bill links work up to that step there. Test real PDFs in Docker.
- Google sign-in is configured in the Google Cloud project "Karobar ERP" (`storied-catwalk-513610-u1`, in testing mode with the owner's Gmail as test user); a duplicate empty "Karobar ERP" project was created by mistake and can be deleted. Facebook is waiting for the owner to sign in at developers.facebook.com.
- Not tested: the v2 checkbox being ticked by a person, Facebook sign-in end to end, a signed bill link returning a real PDF, and the sales screens in Urdu and Arabic by a native reader.

## Next session

Agreed order, one PR each:

1. Review and merge the first M6 piece (`feat/hr-employees`).
2. M6 next: attendance and leave on working days, then the monthly payroll run with income tax from slabs stored as data per tax year (Pakistan first, with official sources), payslips as PDF and the payroll journal entry.
3. Before switching the chat on in production: move each answer to a Celery job the screen polls, so a slow Groq reply or lookup can't hold a web worker.
4. Demand forecasting: a Django app run nightly by Celery, using statsmodels with a simple fallback for thin sales history.

Also check a signed bill link returning a real PDF in Docker.

## Open questions

- A Facebook sign-up keeps its link when the address is confirmed by email, because that is how a real Facebook user confirms. Someone who claims another person's address and gets them to click the link would keep an account on it. Decide how Facebook accounts should be confirmed.
- Reports that read all history stay slow at 1 million lines, on MySQL with its default 128 MB buffer pool: balance sheet and all-time trial balance about 4.7s, cash flow about 7s, dashboard about 4.4s. Each joins every line to its entry. A larger buffer pool should help, which was not measured; the real fix is keeping running balances per account or copying the date onto the line.
- First tax and payroll rules to ship (Pakistan first, then the Gulf), with official sources.
- Chat messages can never be deleted through the app, which is what makes them tamper-evident. Decide how long to keep them before launch.
- Before switching the chat on in production: each question holds a web worker while it builds the figures and waits up to 20 seconds for Groq, and the Dockerfile runs 3 workers, so three people chatting at once could stall the whole API. Options are moving the call to Celery with polling, or caching the figures and adding workers.
- Someone who loses a permission keeps the figures in their old chat replies, and those replies still go to Groq as history. The maintainer accepted this on #34 for now; fixing it needs each reply tagged with what it was allowed to include.
- The chat check can't notice the newest messages being deleted in the database. Catching that needs the latest signature and count stored outside the chat table. Decide if it matters.
- The home page warning after a failed refresh says the server could not be reached, not that the figures on screen may be out of date. The maintainer left it that way on #32; revisit it if shopkeepers misread old figures.
- Dependabot alert 2: `minimatch` (medium), in development dependencies only. Fixed in 11.0.1.
- Groq calls started failing after about a dozen quick questions in testing, probably its rate limit on this key. Check the plan's limits against expected use before switching the chat on in production.
- Chat drafts carry no tax: the card says so and the person adds it on the draft. Products have no default tax rate to take it from. Decide if they should.
- A chat draft's prices are the ones on the card when it was proposed, not when Confirm is pressed. The date is the day of Confirm.
- Deleting an account keeps the address in older audit rows and invitation records, because the audit log is never edited. Decide before launch whether privacy rules need a clean-up job.
