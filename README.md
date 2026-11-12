# Karobar ERP

**Stock, sales, accounts and payroll for small businesses, in one place.**

Karobar ERP is for shops, wholesalers and distributors that run on paper registers or
spreadsheets and find the big ERPs too heavy. One installation serves many businesses (tenants),
each with its own warehouses, customers, books and staff. Every sale, purchase and payment posts
its own double-entry journal entry, so the trial balance, profit and loss and balance sheet are
always up to date. The app speaks English, Urdu and Arabic, right to left where needed.

It is built for people who are not accountants, and who may not read comfortably: plain words, a
picture beside every screen, big buttons, and step-by-step help on each page.

> Status: pre-release, `v0.3.0`. Sign-in, businesses and roles, double-entry accounting and inventory
> work today; purchasing and sales are next. See [docs/roadmap.md](docs/roadmap.md) for the milestones
> and [docs/status.md](docs/status.md) for where the work is.
>
> Website: [karobarerp.ahmershah.dev](https://karobarerp.ahmershah.dev)

## What it does

Inventory and accounting are live; the rest is on the [roadmap](docs/roadmap.md).

- **Inventory.** Products with variants and units, several warehouses, stock moves, batches with
  expiry dates, barcodes, low-stock alerts, and stock valued by FIFO or moving average.
- **Sales.** Quotations, orders, invoices, payments, returns and credit notes, customer credit
  limits, PDF invoices, and a point-of-sale screen for the counter.
- **Purchasing.** Suppliers, purchase orders, goods received and supplier bills.
- **Accounting.** Chart of accounts, journal entries posted by every document, fiscal periods,
  trial balance, profit and loss, balance sheet, and sales tax (GST/VAT) reports.
- **HR and payroll.** Employees, attendance, leave on working days, and monthly payroll with
  payslips.
- **Platform.** Many businesses on one installation, roles and permissions per module, an audit
  log of every change, and English, Urdu and Arabic.

## Stack

| Part | Tools |
|---|---|
| API and jobs | Python 3.12, Django 5.2, Django REST Framework, drf-spectacular, Celery |
| Data | MySQL 8.4 (InnoDB, row locks for stock), Redis (queue and cache) |
| Web | React, TypeScript (strict), Vite, Tailwind CSS, TanStack Query and Table, Recharts, i18next, anime.js |
| Documents | WeasyPrint for PDF invoices, payslips and reports |
| Quality | pytest, factory_boy, Vitest, Ruff, mypy, ESLint, Prettier, GitHub Actions, CodeQL |
| Run | Docker Compose |

## Why it exists

The hard parts of an ERP are not the forms: they are books that always balance, stock that stays
right when two cashiers sell the last item at the same moment, and one business never seeing
another's data. Karobar ERP is built around those three rules, with tests for each.

## Security and speed

- Passwords hashed with Argon2id, with bcrypt as a fallback.
- Session cookies with CSRF protection, a nonce-based Content Security Policy, and rate limits on
  every endpoint.
- Public forms guarded by reCAPTCHA v3, a v2 checkbox when v3 is unsure, and a honeypot field.
- Redis for cache, sessions and throttles; Brotli and gzip compressed at build time; WebP images.
- A service worker keeps the app's code, never business data, so losing the connection shows a
  helpful screen and recovers by itself.

Details are in [docs/security.md](docs/security.md).

## Run it locally

You need Docker, Python 3.12 and Node 22. One command starts everything:

```sh
git clone https://github.com/ahmershahdev/karobar-erp.git
cd karobar-erp
npm run dev
```

The first run creates `backend/.env` with a random secret key, the Python virtual environment and
`node_modules`, starts MySQL and Redis in Docker, applies migrations, then runs Django on :8000,
a Celery worker and Vite on <http://localhost:5173>. Emails (sign-up confirmation, password
reset, invitations) are printed in the worker's log in development. Ctrl+C stops the app
processes; `docker compose stop` stops the databases.

To run the pieces by hand instead:

```sh
git clone https://github.com/ahmershahdev/karobar-erp.git
cd karobar-erp
docker compose up -d mysql redis

cd backend
python -m venv .venv
.venv/bin/pip install -r requirements/dev.txt     # .venv\Scripts\pip on Windows
cp .env.example .env                              # then set DJANGO_SECRET_KEY
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver

cd ../frontend
npm ci
npm run dev                                       # http://localhost:5173, proxies /api to :8000
```

To try it with data, set `DEMO_MODE=true` and a `DEMO_PASSWORD` in `backend/.env`, then run `.venv/bin/python manage.py seed_demo`. It makes two invented businesses, a Pakistani kiryana store and a Dubai trading company, each with a year of purchases, sales, returns, payments and payroll. Sign in as `demo@example.com` (or your `DEMO_EMAIL`). A year takes about half an hour per business on a laptop, because every document goes through the normal posting rules; `--days 30` is quicker. Running it again replaces only the demo businesses.

The test database needs one grant on a fresh MySQL volume; `deploy/mysql/init.sql` does it for
the Compose service.

## Checks

```sh
(cd backend && ruff check . && ruff format --check . && mypy . && pytest)
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
```

## Documentation

- [docs/roadmap.md](docs/roadmap.md): milestones M1 to M7 and what "done" means
- [docs/architecture.md](docs/architecture.md): modules, data model, tenancy and decisions
- [docs/status.md](docs/status.md): current state, updated every session
- [docs/security.md](docs/security.md): tenancy, sessions, CSP, rate limits, locking
- [docs/seo.md](docs/seo.md) and [docs/design.md](docs/design.md)
- [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and
  [SECURITY.md](SECURITY.md)
- [Wiki](https://github.com/ahmershahdev/karobar-erp/wiki): guides for users and self-hosters

## Related

- [HolidayOps](https://github.com/ahmershahdev/holidayops): business-day calendars for countries
  and companies.
- [MarketClock](https://github.com/ahmershahdev/marketclock): trading days and settlement dates
  for stock exchanges.
- [OfflineShelf](https://github.com/ahmershahdev/offlineshelf): Wikipedia reading lists for
  offline use.

## License

[MIT](LICENSE).
