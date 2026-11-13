# Concepts

**Business (tenant).** One installation holds many businesses. Each has its own products,
warehouses, customers, books and staff, and never sees another's.

**Member.** A user who belongs to a business. One person can be a member of several businesses
and switch between them without signing in again.

**Role.** A set of permissions per module, such as "view and create in sales" or "view audit".
Owners can do everything. Each new business starts with a Manager role (everything) and a Viewer
role (view only).

**Invitation.** An emailed link that lets one address join a business with a chosen role. It
works once, for 7 days, and only for a signed-in user with that confirmed email.

**Posting.** When an invoice, bill, receipt or payroll run is posted, its stock moves and its
double-entry journal entry are saved together. Posted documents never change; mistakes are fixed
with reversals and credit notes.

**Chart of accounts.** Every business starts with a standard chart: assets, liabilities, equity,
income, cost of sales and expenses. Groups total their accounts; entries go to the accounts
inside them. Accounts can be added and renamed at any time.

**Fiscal year and periods.** Each business picks the month its fiscal year starts (July by
default). The year is split into months; closing a month stops new entries going into it.

**Journal entry.** Saved as a draft first. Posting checks that debits equal credits, that the date
is in an open period and that every account can take entries, then gives it the next number
(JV-000001, JV-000002, ...). Numbers never skip.

**Tax rates.** Sales tax and VAT rates are data with the dates they apply and where they come
from, so a new rate never changes last year's bills. Karobar works out the tax on every line and
keeps tax collected apart from tax paid, for the sales tax report.

**Stock costing.** Each business chooses moving average or FIFO (first in, first out) when it is
created. Every sale moves the cost of what was sold out of stock and into cost of goods sold.

**The counter.** A till is opened with the cash in the drawer and closed with a count. Each
counter sale is a posted bill with its payment; a short or extra drawer is booked to cash over and
short.

**Payroll.** A month is worked out from each person's contract, leave and attendance, then posted
as one journal entry. See [[Payroll]].

**Business chat.** Each person's questions and answers are signed one after another, so a changed
or removed message is caught by the check button. Messages are kept 90 days.

**Audit log.** Every create, change, post and delete on business data records who made it, when,
what changed and the request it came from. Nobody can edit or delete it.
