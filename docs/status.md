# Project status

Last updated: 2026-11-02. Update at the end of every work session.

## Where we are

M1 (platform skeleton) is complete in code. Two pull requests:

- PR #1 `feat/platform-skeleton`: rules, backend and frontend foundation, security baseline,
  public site, CI. CI is green and the review comments are fixed; it is waiting for the review
  threads to be resolved before the squash merge.
- `feat/m1-accounts-and-members` (stacked on #1): sign-up, email verification, password reset,
  creating a business, members, roles with a permission grid, invitations, the business
  switcher, `npm run dev` at the root. 83 backend tests, 14 frontend tests, all checks clean.
  Walked through in a browser end to end against the live dev stack.

The wiki is live with Getting Started, Self Hosting, Concepts, Security Model and FAQ; its source
is `docs/wiki/`.

## Next session

1. Merge PR #1, rebase `feat/m1-accounts-and-members` onto `main`, open its PR, merge after CI.
2. Apply `.github/rulesets/protect-main.json` (now with required checks) to the repository
   settings, push `docs/wiki/` changes to the wiki, tag `v0.1.0` as a pre-release.
3. Start M2: chart of accounts template, fiscal periods, journal entries through
   `apps/core/journal.py`, gapless numbering with a locked counter row.

## Open questions

- First chart of accounts template and first country for tax and payroll rules.
