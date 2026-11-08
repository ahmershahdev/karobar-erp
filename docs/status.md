# Project status

Last updated: 2026-11-08. Update at the end of every work session.

## Where we are

- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core), `v0.3.0` (M3 inventory), `v0.4.0` (M4 purchasing, sales, documents), `v0.5.0` (M5 counter, tax, reports, report indexes).
- Merged since `v0.5.0` (#32 to #43): the business home page (#32); signed bill links, WhatsApp click-to-chat and the daily summary email (#33); the business chat through Groq with signed messages (#34); chat focus and new chat (#35); confirm before every delete (#36); name, email and password settings (#37); chat screen names per language (#38); handing over a business and deleting an account (#39); chat drafts the person confirms (#40); chat lookups of products, customers and suppliers (#41); line and bill discounts with a limit per role and a Sales discounts account (#42); the Bill design screen with six templates, logo, signature, footer and an 80 mm till roll (#43).
- M6 has started. Two PRs are open:
  - **#44** `feat/hr-employees` into `main`: departments, salary structures (allowances and deductions as a fixed amount or a % of basic, with a monthly preview), employees and contracts. Contracts never overlap and sit inside employment; recording a leaving day ends a longer contract. Every check is green and CodeRabbit's last review found nothing; it waits only for the maintainer's merge (auto mode refuses to merge without a person's review).
  - **#45** `feat/hr-attendance-leave` into `feat/hr-employees`: the work week, public holidays filled from the `holidays` library and editable, kinds of leave, leave in working days with approval and balances, daily attendance, and the nightly job that clears former employees' bank accounts after 90 days and national IDs six years after the tax year they left in. Not yet reviewed by CodeRabbit, which only reviews PRs into `main`.
- Real PDFs were made in the Docker image on 2026-11-07 for all six bill templates, in Urdu and Arabic, on the 80 mm roll and for a 25-line bill; each fits one page except the 25-line bill, which splits cleanly. A signed bill link returning a PDF through the API has still not been tried.
- Not tested by a person in the browser: chat drafts and lookups, discounts, the Bill design screen, and all HR screens. Not tested: the v2 checkbox being ticked by a person, Facebook sign-in end to end, and the sales and HR screens in Urdu and Arabic by a native reader.
- Page text for the business home lives under `business` in the locale files. The public home page owns `home`; mixing them crashed the home page once.
- `npm run dev` also runs Celery beat for scheduled jobs. Celery does not reload, so restart it after changing tasks or email code.
- PDFs need Pango, so they can't be made on the maintainer's Windows machine. Use the Docker image for real PDFs.
- Google sign-in is configured in the Google Cloud project "Karobar ERP" (`storied-catwalk-513610-u1`, in testing mode with the owner's Gmail as test user); a duplicate empty "Karobar ERP" project was created by mistake and can be deleted. Facebook is waiting for the owner to sign in at developers.facebook.com.

## Next session

1. Merge #44 (`gh pr merge 44 --squash` once its threads are resolved). Then point #45 at `main`, merge `main` into `feat/hr-attendance-leave` (the squash means git sees the same files added twice: keep the branch's version), wait for CI and CodeRabbit, fix what is real, resolve the threads and merge.
2. M6 payroll run, one PR: a monthly run per business that takes each employee's contract for the month, pro-rates joiners and leavers, deducts unpaid leave and absences, works out Pakistan income tax by the annualised method (estimate the year's taxable pay, tax it with the slabs, subtract tax already deducted this tax year, spread the rest over the months left), and posts one journal entry (salaries expense against salaries payable and withholding tax payable; both accounts already exist in the standard chart). Then payslips as PDF and a bank transfer list.
3. The tax slabs are data per tax year with their source, editable by the owner. Tax year 2027 (1 July 2026 to 30 June 2027) comes from FBR's Withholding Income Tax Rate Card updated to 30 June 2026 per the Finance Act 2026, section 149 (Division I, Part I, First Schedule, clause 2): nil up to Rs 600,000; 1% of the excess to 1,200,000; 6,000 + 11% to 2,200,000; 116,000 + 20% to 3,200,000; 316,000 + 25% to 4,100,000; 541,000 + 29% to 5,600,000; 976,000 + 32% to 7,000,000; 1,424,000 + 35% above. FBR Circular No. 2 of 2026-27, paragraph 8: the 9% section 4AB surcharge on salaried individuals was withdrawn. Sources: https://download1.fbr.gov.pk/Docs/202681113864992WithholdingTaxRatesCard2027.pdf and https://download1.fbr.gov.pk/Docs/202698139527880CircularNo.2of2026-27.pdf. Check them again when building; the Ordinance prevails over the card.
4. Gulf payroll later and separately: no salary tax, but GOSI or the UAE pension for nationals, end-of-service gratuity and the WPS salary file. Pakistan EOBI and provincial social security after the payroll run.
5. Before switching the chat on in production: move each answer to a Celery job the screen polls, so a slow Groq reply or lookup can't hold a web worker. This is also the fix CodeRabbit asked for on #41 about bounding slow lookups.
6. Demand forecasting: a Django app run nightly by Celery, using statsmodels with a simple fallback for thin sales history.

## Decisions taken on 2026-11-07 and 2026-11-08

- Discounts: a % or amount per line and on the bill, booked to Sales discounts (4250); existing roles start at a 0% limit. Coupons are not wanted yet.
- Bill design: the number prefix is `INV-` by default and editable, never hardcoded. Six templates. Pictures are cleaned as described in `docs/security.md`; there is no virus scanner because uploads are never kept as sent.
- Payroll tax: Pakistan salaried first, from the official text, annualised monthly withholding, owners may edit slabs.
- Former employees: bank account cleared 90 days after leaving; national ID kept six years after the end of the tax year of leaving, longer if the business chooses, never shorter. Names, payslips and journal entries stay.
- Merging: the maintainer merges, or tells the agent to; the main branch needs every review thread resolved before a squash merge.

## Open questions

- A Facebook sign-up keeps its link when the address is confirmed by email, because that is how a real Facebook user confirms. Someone who claims another person's address and gets them to click the link would keep an account on it. Decide how Facebook accounts should be confirmed.
- Reports that read all history stay slow at 1 million lines, on MySQL with its default 128 MB buffer pool: balance sheet and all-time trial balance about 4.7s, cash flow about 7s, dashboard about 4.4s. Each joins every line to its entry. A larger buffer pool should help, which was not measured; the real fix is keeping running balances per account or copying the date onto the line.
- Chat messages can never be deleted through the app, which is what makes them tamper-evident. Decide how long to keep them before launch.
- Before switching the chat on in production: each question holds a web worker while it builds the figures and waits up to 25 seconds for Groq and lookups, and the Dockerfile runs 3 workers, so three people chatting at once could stall the whole API. Moving the call to Celery with polling is the planned fix (step 5 above).
- Someone who loses a permission keeps the figures in their old chat replies, and those replies still go to Groq as history. The maintainer accepted this on #34 for now; fixing it needs each reply tagged with what it was allowed to include.
- The chat check can't notice the newest messages being deleted in the database. Catching that needs the latest signature and count stored outside the chat table. Decide if it matters.
- The home page warning after a failed refresh says the server could not be reached, not that the figures on screen may be out of date. The maintainer left it that way on #32; revisit it if shopkeepers misread old figures.
- Dependabot alert 2: `minimatch` (medium), in development dependencies only. Fixed in 11.0.1.
- Groq calls started failing after about a dozen quick questions in testing, probably its rate limit on this key. Check the plan's limits against expected use before switching the chat on in production.
- Chat drafts carry no tax: the card says so and the person adds it on the draft. Products have no default tax rate to take it from. Decide if they should.
- A chat draft's prices are the ones on the card when it was proposed, not when Confirm is pressed. The date is the day of Confirm.
- After the chat saves a draft, its link opens the document's list, not the draft itself, because document screens can't open one document from a link yet (CodeRabbit on #40).
- Deleting an account keeps the address in older audit rows and invitation records, because the audit log is never edited. Decide before launch whether privacy rules need a clean-up job.
