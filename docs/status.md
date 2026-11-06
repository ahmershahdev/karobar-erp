# Project status

Last updated: 2026-11-07. Update at the end of every work session.

## Where we are

- Released: `v0.1.0` (M1 platform), `v0.2.0` (M2 accounting core), `v0.3.0` (M3 inventory), `v0.4.0` (M4 purchasing, sales, documents), `v0.5.0` (M5 counter, tax, reports, report indexes).
- Merged since `v0.4.0`: #25 to #31. The latest are the counter (#28), password reset for accounts with no password (#29), report indexes (#30), and branded emails, themed dropdowns, signed-in links and counter store handling (#31).
- Open: #32 (`feat/business-home`), the business home page with a setup checklist, figures, warnings and a sales chart. Two minor review points remain, and the maintainer decides them.
- Built, on GitHub, no PR yet: `feat/ai-assistant`, stacked on #32. It holds two pieces, to go in as two PRs:
  - Signed bill links, WhatsApp click-to-chat, and a daily summary email (`apps/sales/links.py`, `apps/core/whatsapp.py`, `apps/reports/tasks.py`).
  - The business chat through Groq with signed messages (`apps/assistant`, `apps/core/chain.py`). See `docs/security.md`.
- Page text for the business home lives under `business` in the locale files. The public home page owns `home`; mixing them crashed the home page once.
- `npm run dev` also runs Celery beat for scheduled jobs. Celery does not reload, so restart it after changing tasks or email code.
- PDFs need Pango, so they can't be made on the maintainer's Windows machine. Printing and signed bill links work up to that step there. Test real PDFs in Docker.
- Google sign-in is configured in the Google Cloud project "Karobar ERP" (`storied-catwalk-513610-u1`, in testing mode with the owner's Gmail as test user); a duplicate empty "Karobar ERP" project was created by mistake and can be deleted. Facebook is waiting for the owner to sign in at developers.facebook.com.
- Not tested: the v2 checkbox being ticked by a person, Facebook sign-in end to end, a signed bill link returning a real PDF, and the sales screens in Urdu and Arabic by a native reader.

## Next session

1. Decide the two review points on #32, then merge it.
2. Rebase `feat/ai-assistant` onto `main` and open its two PRs: WhatsApp and automation first, then the chat.
3. M6: HR and payroll, starting with employees, departments, contracts and salary structures.

## Open questions

- A Facebook sign-up keeps its link when the address is confirmed by email, because that is how a real Facebook user confirms. Someone who claims another person's address and gets them to click the link would keep an account on it. Decide how Facebook accounts should be confirmed.
- Reports that read all history stay slow at 1 million lines, on MySQL with its default 128 MB buffer pool: balance sheet and all-time trial balance about 4.7s, cash flow about 7s, dashboard about 4.4s. Each joins every line to its entry. A larger buffer pool should help, which was not measured; the real fix is keeping running balances per account or copying the date onto the line.
- First tax and payroll rules to ship (Pakistan first, then the Gulf), with official sources.
- Chat messages can never be deleted, which is what makes them tamper-evident. Decide how long to keep them before launch.
