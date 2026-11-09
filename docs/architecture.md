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
| `reports` | trial balance, P&L, balance sheet, tax and stock reports, the business home figures, the daily summary |
| `assistant` | the per-person business chat through Groq, with signed messages and confirm-first drafts |
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
| A counter sale is an invoice and a receipt | One atomic post for the walk-in customer, so stock, books, reports and returns need no second path. Prices come from the product on the server, never from the request. One open till per store is enforced by a unique key that is cleared on closing, because MySQL has no partial unique index. A till difference is booked to cash over and short. |
| Report indexes are measured, not guessed | Checked on 1.1 million journal lines and 1.1 million invoice lines: the dashboard went from 19.5s to 4.4s and document lists from about 1s to under 10ms. The entry number key leads with the number, because led by tenant it beat the (tenant, status, date) index in the planner. Reports grouped over every account stay on the plain filter, which measured faster. A covering index on journal lines was tried and gave nothing. |
| Discounts come off before tax and show on their own account | A line takes a percentage or an amount off; the bill discount is then spread over the lines in proportion to what is left, from rounded running totals (`apps/core/documents.spread`), so the parts add back exactly. Tax is worked out on each line's remainder, and a line's `amount` is that remainder, so returns, margins and reports read discounted figures without change. Posting keeps the full price in Sales and debits Sales discounts (4250) with what was given, so the profit and loss shows it. Each role has a maximum discount percentage per line, counting its share of the bill discount; the owner has none. Lines carried over from an order were checked when the order was saved. |
| The chat drafts, a person confirms | The model only names a customer, supplier and products; the server finds them and fills unit, price and warehouse, and the person presses Confirm before the document's own save runs. A name that doesn't match one record comes back as a coded card the app words in the person's language, so there is no second, slower call to the model. Drafts only: posting, paying and deleting stay on the screens. |
| Pay comes from a contract and a shared structure | A salary structure lists allowances and deductions, each a fixed amount or a percentage of basic and marked taxable or not; a contract gives one employee a structure and a basic salary over dates. Contracts for one person never overlap, checked under a lock on the employee, so the pay on any day is never in doubt; a raise is a new contract from the next day. The month's arithmetic is `apps/core/payroll.breakdown`. Income tax is worked out by the payroll run, because the slabs are data per tax year. Employees with contracts are marked as left, never deleted. |
| Payroll is worked out, checked, then posted | A month's run is a draft that can be worked out again as often as needed; posting fixes its payslips and books one entry: Dr salaries, Cr withholding tax payable, Cr payroll deductions payable (2170), Cr salaries payable. Pay is by calendar day, so joiners, leavers and a raise mid-month pay each contract for its days, and approved unpaid leave and absences (a half day counts half) come off on working days only. Payslips keep a copy of their lines, so a later change to a structure never rewrites them. Posting works the month out once more and, if anything changed since the draft, updates the draft instead, so nobody posts figures they haven't seen. |
| A posted payroll is undone by a reversal | Posted entries never change, so undoing a month posts the reversal of its entry on the same date, and the month's books net to nothing. The run stays, marked reversed, with its payslips and number as history, and the month can be worked out again: a month has one live run, kept by a `live_month` key that is cleared on reversal, because MySQL has no partial unique index. A paid month can't be undone (the money has left), and nor can a month once a later month of its tax year is posted, because that month's tax counted it; undo from the latest back. |
| Salaries are paid in a second step | Posting books the month's salaries as owed; paying them happens later, often in the next month, from one cash or bank account, so it is its own step: Dr salaries payable, Cr that account, for the month's total net pay, dated when the money left and never before the month starts. A month is paid once and all at once. The bank transfer list is a CSV of each person's bank account and net pay. |
| Salary tax by the annualised method, from slabs as data | Each tax year's slabs are a table with its dates and the law it comes from (`apps/payroll/data/tax_tables.json` ships Pakistan's tax year 2027 from the Finance Act 2026, read from FBR's rate card); the owner can add or correct years, and a table that posted payroll used can't change. Each month estimates the year's taxable salary from this tax year's posted payslips plus this month's pay for every month left, works out the year's tax, takes off what was withheld, and spreads the rest over the months left (`apps/core/salary_tax.py`). That only adds up if months are posted in order, so an earlier draft blocks posting and a later posted month blocks working out. The UAE and Saudi Arabia have no tax on salaries, so they need no table. Taxable salary and tax from earlier in the year (months before the business used payroll here, or a previous employer's certificate) are typed in as pay before Karobar and count with the posted payslips; they can only change while the person has no posted pay here that tax year. |
| One bill design per business | Details, wording, footer, colour, columns and counter paper live in one `BillSettings` row; until it is saved, the defaults apply, so older businesses print as before. The number prefix stays on the invoice number series, so posting still reads it in one place and the counter carries on across a change. The logo is stored in the database as a small PNG the app wrote, which needs no file storage or extra service. The 80 mm layout is for counter sales only; other bills stay A4. The six templates are style sets in one print sheet, picked by a class on the page, so every template prints the same content and only looks different. |
| EOBI and social security as data, only official figures shipped | Each rate (EOBI or provincial social security, one province or all, the employer's and the employee's percent, worked out on the province's minimum wage or on the month's pay up to a ceiling) and each province's minimum wage is a row with the day it starts and its source; it holds until a later row replaces it, as notifications do. Only figures read from an official notification ship in `apps/payroll/data/contributions.json`: the Islamabad and Sindh minimum wages from 1 July 2026. EOBI's percentages are not shipped: the copy of the EOBI Act found says six percent of wages from the employer and Rs 20 from the employee, while every guide says 5% and 1% of the minimum wage, and the amending text wasn't found; the business enters its own from its challan. Each employee has a work province and two switches (pays EOBI, pays social security), off by default because coverage depends on business size, age and a wage limit that aren't recorded. The staff's share is a deduction line, not taxable pay; the business's share is stored on the payslip. Posting books Dr employer contributions (6150), Cr EOBI and social security payable (2180) for both shares. A run that needs a missing rate or minimum wage names it and stops. On the minimum wage, a person on the payroll any day of the month pays the whole month, as the institutions charge per insured person per month. |
| Gulf social insurance by nationality, rates entered by the business | The contribution rates that serve EOBI also hold Saudi GOSI (annuities, SANED, occupational hazards) and the UAE pension (GPSSA). A Gulf rate says who pays (everyone, nationals or everyone but nationals, against the business's country), optionally that it is only for people first insured from a date (GOSI's new system from 3 July 2024, against each employee's first-insured date or else their joining day), and what it is worked out on: the month's pay, or the insurable wage, a full month of basic plus the pay parts marked as counting (GOSI counts basic and housing), with a ceiling and a floor. For each scheme the most particular rate covering the person wins. Pakistan keeps its per-person switches and province. No Gulf rate ships, because no official text could be read (gosi.gov.sa and gpssa.gov.ae refused the connection); a Gulf scheme with no rate is not charged. Both shares post as EOBI does: Dr employer contributions (6150), Cr contributions payable (2180). |
| End-of-service gratuity built up monthly, paid once | In the UAE and Saudi Arabia each country's rule is a row with the law it is read from (`apps/payroll/data/gratuity.json`): UAE Federal Decree-Law 33 of 2021 Article 51 (21 days of basic wage a year for five years, then 30; nothing before a year; at most two years' wage; unpaid absence left out; nationals excluded, as their end of service is a pension) and Saudi Labor Law Articles 84 and 85 (half a month of the full wage a year for five years, then a month; on resignation a third from two to five years, two thirds after five, all from ten). Shares are fractions so a third stays exact. Every posted month books the change in each person's award so far, worked out as if they left at the month's end: Dr end-of-service benefits (6160), Cr end-of-service provision (2190). Because each month counts the one before, Gulf months are posted in order, like Pakistan's tax year. When someone leaves and their last month is posted, the payout uses up the provision and books the difference (a Saudi resignation gives some back), Dr provision, Dr or Cr the expense, Cr cash or bank. A month that fed a paid gratuity can't be undone. A day's wage is a thirtieth of the month; service is days over 365. |
| Holidays are the business's own list | The `holidays` library only fills the list in; each holiday is a row with its source, because Eid and other moon-sighted days are estimates until announced, and the business corrects them. Refilling never overwrites a day already there. The weekend is a setting (Sunday in Pakistan, Saturday and Sunday in the UAE). Leave counts working days from both when it is asked for and keeps that number, and a request stays inside one calendar year (leave over New Year is two requests), because allowances are yearly, so a holiday added later doesn't change leave already approved. Approval checks the yearly allowance under a lock on the employee. Approved leave can be cancelled, all of it or from the day someone came back, which counts the remaining working days again and gives the rest back; unpaid days in a month whose payroll is posted already came off the pay, so they stay until that payroll is undone. Attendance stores only what differs from present; approved leave shows by itself. |
| WhatsApp opens, a person sends | Click-to-chat links are free and need no account with Meta. Sending by itself would need the WhatsApp Business API, with approval and a fee per message. |
| Tax rates are data with a source | Each rate records its dates and the notice behind it, and rates are never in code. A chosen rate decides a sales line's tax on the server, rounded once per line; a rate used on a document can only be ended, not deleted. Supplier bills keep the tax as printed on the supplier's invoice. |
| Reports read the journal, margins read documents | Anything that must agree with the books comes from journal lines. Only an invoice knows which product sold at what cost, so sales and margin come from documents. Income and expenses aren't closed by a year-end entry; the balance sheet adds profit to date, which is what makes it balance. |
| PDFs render on the server, and only there | WeasyPrint needs Pango, which the Docker image has and Windows usually doesn't. The import happens at print time, so everything else runs without it, and a machine without it answers 503 with a plain message rather than crashing. |
| A quotation and an order are one document | A quote becomes an order by changing stage, so nothing is typed twice. A draft takes a QUO number when quoted and an SO number when confirmed. |
| Credit limits are checked under the customer's lock | Two sales at once can't both pass on the same balance. Empty means no limit and zero means cash only; an advance adds to what a customer may buy. |
| Returns come back at the cost they left at | A credit note restocks at the invoice line's booked cost and reverses cost of goods sold, so the sale's profit is undone exactly. Whatever can't come off the invoice stays on the account as credit. |
| Business slugs are for addresses only | `/app/al-madina-traders` reads better than a UUID, but the API still takes `public_id` in `X-Tenant`. The app resolves a slug against the user's own memberships, so knowing one gives nothing away, and a slug never changes when a business is renamed, so links keep working. |
| Sign-in screens live at the root | `/login` and `/signup` are what people expect and can type. `/app` holds only the workspace. Old addresses redirect with their query string, because emails already sent still use them, and those words are reserved so no business can take them as a slug. New screens go in `AUTH_PATHS` in `lib/paths.ts` and in the nginx list: unknown addresses are real 404s. |
| Brotli without an nginx module | The official nginx image has no Brotli. The build writes `.br` and `.gz` files and nginx picks one with a `map`. Dynamic gzip must stay off for those locations: it can't see `add_header` and would compress the `.br` file again. |
| A service worker for offline, not offline data | It keeps the app's code so an offline visit gets a helpful screen rather than the browser's error. Business data is not cached: a shop's books must never look current when they aren't. |
| Books set up through a `tenant_created` signal | Tenancy doesn't import accounting; later modules hook in the same way |

## Open questions

- Gulf payroll: social security (GOSI, the UAE pension), end-of-service gratuity and WPS salary
  files, each from official sources before it is coded. Pakistan's salary tax ships first.
- Paying part of a month (some people now, some later) isn't built; a month is paid all at once.
- Whether HR uses the `holidays` library directly or the HolidayOps API for working days.
