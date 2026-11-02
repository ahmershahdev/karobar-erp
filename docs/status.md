# Project status

Last updated: 2026-11-02. Update at the end of every work session.

## Where we are

Planning. The repository, roadmap, architecture draft, rulesets and GitHub milestones are set up;
no code yet. Next: M1 (platform skeleton), see [roadmap.md](roadmap.md).

## Next session

1. M1: Django project with settings per environment, Docker Compose with MySQL 8.4, Redis and one
   Celery worker, pytest, Ruff, mypy; Vite + React + TypeScript app.
2. Add the `backend`, `frontend` and `codeql` CI jobs, then make them required checks in the
   "Protect main" ruleset (`.github/rulesets/protect-main.json` and the repository settings).

## Open questions

- Tenant selection: header with a tenant switcher, or one subdomain per tenant.
- First chart of accounts template and first country for tax and payroll rules.
