# Project status

Last updated: 2026-11-07. Update at the end of every work session.

## Where we are

- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core), `v0.3.0` (M3 inventory), `v0.4.0` (M4 purchasing, sales, documents), `v0.5.0` (M5 counter, tax, reports, report indexes).
- Merged since `v0.5.0`: the business home page (#32), signed bill links, WhatsApp click-to-chat and the daily summary email (#33), and the business chat through Groq with signed messages (#34, `apps/assistant`, `apps/core/chain.py`; see `docs/security.md`).
- `feat/ai-assistant` is replaced by #33 and #34 and can be deleted.
- Page text for the business home lives under `business` in the locale files. The public home page owns `home`; mixing them crashed the home page once.
- `npm run dev` also runs Celery beat for scheduled jobs. Celery does not reload, so restart it after changing tasks or email code.
- PDFs need Pango, so they can't be made on the maintainer's Windows machine. Printing and signed bill links work up to that step there. Test real PDFs in Docker.
- Google sign-in is configured in the Google Cloud project "Karobar ERP" (`storied-catwalk-513610-u1`, in testing mode with the owner's Gmail as test user); a duplicate empty "Karobar ERP" project was created by mistake and can be deleted. Facebook is waiting for the owner to sign in at developers.facebook.com.
- Not tested: the v2 checkbox being ticked by a person, Facebook sign-in end to end, a signed bill link returning a real PDF, and the sales screens in Urdu and Arabic by a native reader.

## Next session

Agreed order, one PR each:

1. Keep the chat to the business, with short replies and a new chat button.
2. Ask before every delete. All 13 delete actions in the app fire on one click.
3. Account settings: change name, email and password, and delete an account by anonymising it. None of this exists yet.
4. Chat tasks: drafts only, shown as a card the person confirms. Never posting, paying or deleting.
5. M6: HR and payroll, starting with employees, departments, contracts and salary structures.
6. Demand forecasting: a Django app run nightly by Celery, using statsmodels with a simple fallback for thin sales history.

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
