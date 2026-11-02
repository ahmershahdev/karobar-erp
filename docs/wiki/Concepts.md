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

**Audit log.** Changes to businesses, members, roles and invitations record who made them, when,
what changed and the request they came from. Each business module adds its own records as it
ships.
