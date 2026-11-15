# Testing

What is tested, how to run each kind of test, and what the runs on 2026-11-14 found. Unit and
API tests live beside the code (`backend/tests`, `frontend/src/**/*.test.*`); this page is about
the tests that need a running system.

## The kinds of test

| Kind | Where | What it answers |
|---|---|---|
| Unit and API | `backend/tests` (pytest, MySQL), `frontend/src` (Vitest) | Does each rule hold: balanced entries, stock, numbering, tenancy, permissions |
| Smoke | `e2e/tests/smoke.spec.ts` | Does every screen open with real data and no error, in three languages, on desktop and phone |
| Functional and acceptance | `e2e/tests/journey.spec.ts` | Can a new shopkeeper sign up, confirm the email, create a business, reset a password, sign out |
| Security | `e2e/tests/security.spec.ts` | The rules in [security.md](security.md), checked from outside a running server |
| Load and stress | `loadtest/staff.js` (k6 in Docker) | What happens when 10, 25 and 50 staff of one business work at once |
| Data migration | commands below | Migrations are complete, apply from nothing and reverse |

## End-to-end tests (Playwright)

They run a real Django server and the real React app on their own ports (8001 and 5174), their
own database (`test_karobar`) and their own Redis database, so a running `npm run dev` is not
touched. Settings are `config.settings.e2e`: mail is written to files the tests read, jobs run
in the request, and reCAPTCHA, the chat model and social sign-in are off.

```sh
docker compose up -d --wait mysql redis
cd e2e
npm ci
npx playwright install chromium
npm run seed        # empties test_karobar, makes the demo businesses and the test people
npm test            # starts both servers itself
npm run test:smoke  # the smoke tests only
```

- `npm run seed` takes a few minutes, because every demo document is really posted. It refuses
  to run on a database whose name does not start with `test_` or `e2e_`.
- The seed and pytest share `test_karobar`. After the end-to-end tests run pytest once with
  `--create-db`, and seed again before the next end-to-end run.
- In a git worktree set `E2E_PYTHON` to the Python of the main folder's virtual environment.
- A new screen goes into `SCREENS` in `e2e/tests/helpers.ts`; a test fails if the menu links to
  a screen that list does not have.
- Tests find buttons by the app's own text from the locale files, so rewording a label does not
  break them.

### What the smoke tests check on every screen

45 screens, for the Hyderabad store in English and Urdu and the Dubai company in English and
Arabic, at desktop and phone width: the address stays where it was sent, the page direction
matches the language, a heading is shown, the "server could not be reached" message is not, the
page is no wider than the window, the console has no error, and no API call fails.

### What the security tests check

Nothing private answers without a session; the app sends a stranger to sign in; the session
cookie is HttpOnly and SameSite=Lax and nothing about the session is in browser storage; the
security headers are present; a change without the CSRF token is refused; one business gets 404
for another business's id and rows; a cashier's role is refused everything but the counter and
the menu hides the rest; a name containing HTML and a spreadsheet formula is shown as text; a
search that looks like SQL is only a search; a body over 2 MB is refused with 413; the shared
demo account cannot create a business or change its password; errors show nothing about how the
server is built.

## Load and stress test (k6)

Fifty staff accounts (`load1@e2e.test` to `load50@e2e.test`, made by the seed) work in the demo
store. A quarter read lists, a quarter read reports, a quarter add customers and a quarter make
and post sales bills for the same five products from the same store, which is where stock
levels, bill numbers and the books are under contention. The run climbs to 10, then 25, then 50
people. It fails if any answer is a server error or is wrong, and afterwards it checks that the
trial balance still balances.

```sh
cd e2e && npm run seed
# start the API the way the end-to-end tests do, or let `npm test` leave it running
docker run --rm -v "$PWD/../loadtest:/scripts" grafana/k6:2.4.0 run /scripts/staff.js
```

`PEAK` (default 50) and `HOLD` (default `2m`) change the size and length of the run.

## Data migration

```sh
cd backend
python manage.py makemigrations --check --dry-run   # no model change without a migration
pytest --create-db                                   # every migration applies from nothing
python manage.py migrate assistant 0005 && python manage.py migrate   # the newest one reverses
```

## Results on 2026-11-14 and 2026-11-16

Run on the maintainer's laptop while a demo rebuild was also running, so the timings are slow
and say little about a real server.

| Run | Result |
|---|---|
| pytest | 1148 passed, 97.1% coverage (the gate is 95%; `apps/core` is at 100% branch coverage) |
| Vitest | 44 passed |
| End-to-end, first runs | Smoke found the phone layout bug, the journey the new-business bug, security the 2 MB bug (all below) |
| End-to-end, full run on 2026-11-16 after the fixes | 44 passed, 1 skipped by design, in 35 minutes: journey 8, security 11, smoke 13 on desktop and 12 on a phone |
| Load, 10 people | 0 server errors, 0 wrong answers, 95% of requests under 0.3 s |
| Stress, 50 people | 4 server errors in about 380 bill postings; fixed below |
| Migrations | none missing; apply from nothing; `assistant.0006` reverses and re-applies |

### Bugs these runs found, all fixed in the same branch

1. **Phone layout.** Tax slabs was 234px and Social insurance 22px wider than the window, in
   every language, because a long source link could not wrap. Sources now wrap on those two
   screens, End of service and Holidays.
2. **Creating a business sent you back.** After Create, a first-time owner landed on the New
   business form again, and someone with a business landed on the old one. The list of
   businesses was stale at the moment of moving on. The new business is now put in the list
   first.
3. **A body over 2 MB was a server error** when Django was reached without nginx. It is now
   refused with 413.
4. **Giving up on a row lock was a server error.** With 50 people, about a dozen posting bills
   for the same products at once, a posting that was still waiting for a lock after three tries
   (about 40 seconds) answered 500. Nothing was saved and the books stayed balanced, but the
   message was wrong. It now answers 503 "Many people are saving at once. Nothing was saved;
   please try again." The cause was read from the timings, not from a captured traceback: the
   repeat run sold out of stock before it happened again.

### What the stress run says

At 50 people on the development server, posting a bill took 2 s at the median and 12 s at the
90th percentile. Posting is one transaction that locks the number series, the stock levels and
the fiscal period, so people selling the same product queue behind each other. That is the
design, and it kept every number unique and the books balanced. Before launch the same run
should be repeated against gunicorn behind nginx on the real server, where the numbers mean
something.

## Not tested yet

- The load test against the production stack (gunicorn, nginx, its rate limits and compression).
  The rate limits were therefore not exercised: the end-to-end settings raise them.
- Screens beyond opening them: making a product, a purchase, a sale at the counter, a payroll
  run through the browser. The API tests cover those rules; no browser test does yet.
- The chat against a real or fake Groq in the browser (see [chat-fixes.md](chat-fixes.md)).
- Firefox and Safari. Real phones. A screen reader.
- Upgrading a copy of a large production database; there is no production data yet.
- Coverage is 97%, not 100%. The uncovered lines are mostly error branches in views.
