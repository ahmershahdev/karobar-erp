# Project status

Last updated: 2026-11-09. Update at the end of every work session.

## Where we are

- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core), `v0.3.0` (M3 inventory), `v0.4.0` (M4 purchasing, sales, documents), `v0.5.0` (M5 counter, tax, reports, report indexes).
- Merged since `v0.5.0` (#32 to #43): the business home page (#32); signed bill links, WhatsApp click-to-chat and the daily summary email (#33); the business chat through Groq with signed messages (#34); chat focus and new chat (#35); confirm before every delete (#36); name, email and password settings (#37); chat screen names per language (#38); handing over a business and deleting an account (#39); chat drafts the person confirms (#40); chat lookups of products, customers and suppliers (#41); line and bill discounts with a limit per role and a Sales discounts account (#42); the Bill design screen with six templates, logo, signature, footer and an 80 mm till roll (#43).
- M6: employees, departments, salary structures and contracts (#44) and the work week, holidays, leave, attendance and former-employee retention (#45) are merged. Review fixes on #45: holiday names in a fixed language, IDs and bank accounts kept out of the audit log, leave inside one calendar year, current contracts in one query, HR's own menu heading.
- In review: `feat/gulf-insurance`. Saudi GOSI (annuities, SANED, occupational hazards) and the UAE pension on the Social insurance screen (renamed from EOBI and social security): who pays by nationality, GOSI's new system by a first-insured date on each employee, worked out on pay or on the insurable wage (basic plus parts ticked on the salary structure) with a ceiling and a floor. No Gulf rate ships.
- Merged: `feat/gratuity` (#57), checked in the browser on 2026-11-09 on Payroll Check Traders (now set to Saudi Arabia, December 2026 and January 2027 posted, E3 left on 15 January 2027 with the gratuity unpaid). End-of-service gratuity in the UAE and Saudi Arabia: rules as data from UAE Article 51 and Saudi Articles 84 and 85 on a new End of service screen, a nationality on each employee, a monthly provision booked with the payroll (Dr 6160, Cr 2190), and the payout on the employee's screen once their last month is posted, by reason (ended or resigned). The law texts were read from English translations (FAOLEX for the UAE, WIPO Lex for Saudi Arabia); the Arabic texts govern, and the Saudi 2024 amendments (Royal Decree M/44) were not checked.
- Merged: `feat/social-security` (#56). EOBI and provincial social security: rates and minimum wages as dated data with sources on a new EOBI and social security screen, a work province and two switches per employee, the staff share as a payslip deduction, the employer share booked Dr 6150 Cr 2180, and a table on the payslip PDF. Only the Islamabad (Rs 40,700) and Sindh (Rs 43,000) minimum wages from 1 July 2026 ship, from their notifications; EOBI percentages, other provinces' wages and every social security rate are entered by the business, because no official text was found for them (the copy of the EOBI Act found says 6% of wages and Rs 20, guides say 5% and 1% of the minimum wage).
- Merged: `feat/cancel-leave` (#51). Approved leave can be cancelled in full or from the day someone came back early, giving the days back; unpaid days in a posted payroll month are refused until that payroll is undone.
- Merged: `feat/payroll-reversal` (#50). A posted, unpaid month is undone by reversing its entry on the same date; the run stays as history and the month can be worked out again. Undo goes from the latest posted month back.
- Merged: `feat/salary-payments` (#49). A posted month is paid in one step from a cash or bank account (Dr salaries payable, Cr that account), with a bank transfer list as CSV that needs HR rights and guards against spreadsheet formulas.
- Merged: `fix/payroll-polish` (#47), checked in the browser in English and Urdu after merging: pay before Karobar (taxable salary and tax from earlier in the tax year, so a business starting payroll mid-year withholds the right tax), number column headings that line up on every screen, the days column in Urdu and Arabic, a neutral notice colour, and a link to Tax slabs when they are missing. Found by trying the payroll screens in the browser on 2026-11-09.
- Merged: `feat/payroll-run` (#46). Tax tables as data (Pakistan tax year 2027 ships from the Finance Act 2026, editable, fill-in button), monthly payroll runs worked out by calendar day from contracts with unpaid leave and absences taken off, income tax by the annualised method, posting in month order with one journal entry, and payslips as PDF on the business letterhead. Payroll has its own rights. Measured: 500 people work out in about 0.5s and post in about 0.3s. Payroll screens were tried in the browser on 2026-11-09 in English and Urdu; real payslip PDFs were made in Docker in all three languages.
- Real PDFs were made in the Docker image on 2026-11-07 for all six bill templates, in Urdu and Arabic, on the 80 mm roll and for a 25-line bill; each fits one page except the 25-line bill, which splits cleanly. A signed bill link returning a PDF through the API has still not been tried.
- Not tested by a person in the browser: chat drafts and lookups, discounts, the Bill design screen, and all HR screens. Not tested: the v2 checkbox being ticked by a person, Facebook sign-in end-to-end, and the sales and HR screens in Urdu and Arabic by a native reader.
- Page text for the business home lives under `business` in the locale files. The public home page owns `home`; mixing them crashed the home page once.
- `npm run dev` also runs Celery beat for scheduled jobs. Celery does not reload, so restart it after changing tasks or email code.
- PDFs need Pango, so they can't be made on the maintainer's Windows machine. Use the Docker image for real PDFs.
- Google sign-in is configured in the Google Cloud project "Karobar ERP" (`storied-catwalk-513610-u1`, in testing mode with the owner's Gmail as test user); a duplicate empty "Karobar ERP" project was created by mistake and can be deleted. Facebook sign-in is off at launch by the maintainer's decision (`FACEBOOK_SIGN_IN`, see docs/security.md); to switch it on later, confirming a Facebook sign-up must drop the unproven link and Facebook must be connected from My account while signed in.

## Next session

1. Merge `feat/gulf-insurance` after review and a check in the browser. Then the WPS salary file, then M7. #56 (EOBI) has still not been tried in the browser.
2. Find the official EOBI contribution text (the amendment to section 9 of the EOBI Act 1976, or an EOBI circular) and the provincial social security rates and ceilings; add them to `apps/payroll/data/contributions.json` only with that source.
3. The tax year 2028 slabs (from 1 July 2027) need adding once the Finance Act 2027 is out; payroll for July 2027 will refuse to run until a table covers it.
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
