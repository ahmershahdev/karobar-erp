# Project status

Last updated: 2026-11-02. Update at the end of every work session.

## Where we are

M1 in progress on branch `feat/platform-skeleton` (not merged yet).

Done this session:

- Rules written down: AGENTS.md now has security, SEO, design and comment rules, with details in
  `docs/security.md`, `docs/seo.md` and `docs/design.md`.
- Backend: Django 5.2 with `dev`/`test`/`prod` settings, custom `User` (email sign-in, public UUID),
  session sign-in with CSRF, tenants, roles, memberships, a fail-closed tenant manager, the
  `X-Tenant` middleware, the audit log, health check, request ids, security headers, nonce CSP,
  throttles, cursor pagination, a safe error handler and `lock_rows()`. `apps/core` has money
  rounding and journal balancing at 100% branch coverage, plus a test that it never imports Django.
- 46 backend tests on MySQL 8.4; Ruff, strict mypy and `check --deploy` are clean.
- Frontend: React 19, Vite 8, Tailwind 4, Lenis, three.js hero shader, anime.js reveals and page
  transitions, English, Urdu and Arabic with right-to-left layouts, sign-in screen. Per-route HTML
  heads, JSON-LD, sitemap, robots, llms.txt and llms-full.txt are generated at build.
- Production: nginx with a per-request CSP nonce, edge rate limits and caching rules (checked in a
  browser: no CSP violations); `deploy/compose.prod.yaml`; CI for backend, frontend and CodeQL;
  Dependabot for pip, npm, Docker and Actions.
- Community files: CODE_OF_CONDUCT.md; wiki source in `docs/wiki/`.

## Next session

1. Open the PR for `feat/platform-skeleton`, get CI green, then make `backend`, `frontend` and
   CodeQL required checks in the "Protect main" ruleset.
2. Push `docs/wiki/` to the GitHub wiki (create the first wiki page in the web UI once so the wiki
   repository exists).
3. Finish M1: sign-up, email verification, password reset (all with the `auth` throttle),
   invitations, and a tenant switcher in the app shell.
4. Write audit rows from a service layer helper so every M2 model gets them by default.

## Open questions

- First chart of accounts template and first country for tax and payroll rules.
- The domain in AGENTS.md was `karobar.ahmershah.dev`; it is now `karobarerp.ahmershah.dev`
  everywhere, as asked on 2026-11-02.
