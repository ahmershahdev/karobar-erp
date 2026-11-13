# Contributing

Karobar ERP has its business modules built (accounting, inventory, purchasing, sales, the counter,
tax, reports, HR and payroll) and is getting ready for `v1.0.0`. Issues and ideas are welcome;
for code, please open an issue first so we can agree on the approach. Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Questions go to
[Discussions](https://github.com/ahmershahdev/karobar-erp/discussions).

## Setting up

Follow "Run it locally" in the [README](README.md). To work with realistic data, turn on demo mode
and run `manage.py seed_demo` as described there; it makes two invented businesses. Before
pushing, run the checks listed in the README; CI runs the same ones plus CodeQL and SonarCloud,
and CodeRabbit reviews every pull request.

## Pull requests

- One change per pull request, into `main`, squash-merged.
- Branch names: `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Tests and linters must pass. Business logic in `backend/apps/core` needs 100% branch coverage.
- New tenant-owned endpoints need an isolation test (another tenant's data is `404`); the test
  suite fails until every route is listed in `backend/tests/tenancy/test_isolation.py`.
- API changes regenerate `backend/openapi.yaml` and `frontend/src/lib/api/schema.d.ts`.
- New public pages follow [docs/seo.md](docs/seo.md); visual changes use the tokens in
  [docs/design.md](docs/design.md); anything security-relevant is checked against
  [docs/security.md](docs/security.md).
- Comments only where the code can't speak for itself: the why, a business rule with its source,
  or a trap.
- Never put real customer, supplier or employee data in issues, tests or seed data.
- Text the user sees goes in all three locale files (`en`, `ur`, `ar`), then
  `npx prettier --write` on them. Write it plainly; see the writing rules in [AGENTS.md](AGENTS.md).
- Tax rates, slabs, contributions and other legal figures ship only with an official source
  written next to them. If no official text can be found, the business enters the figure itself.
- Read [AGENTS.md](AGENTS.md) for the code rules and [docs/](docs/) for the design.
