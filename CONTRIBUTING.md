# Contributing

Karobar ERP is early: the platform skeleton is in place and the business modules are being built.
Issues and ideas are welcome; for code, please open an issue first so we can agree on the
approach. Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Questions go to
[Discussions](https://github.com/ahmershahdev/karobar-erp/discussions).

## Setting up

Follow "Run it locally" in the [README](README.md). Before pushing, run the checks listed there;
CI runs the same ones plus CodeQL.

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
- Read [AGENTS.md](AGENTS.md) for the code rules and [docs/](docs/) for the design.
